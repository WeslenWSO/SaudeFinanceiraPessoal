"""Baixas de contas a receber a partir de parcelas conciliadas no Conta Azul (extrato CA)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from contasareceber.models import BaixaContaAReceber, ContaAReceber
from dashboard.conta_azul.client import ContaAzulClient
from dashboard.conta_azul.sync import (
    _aplicar_campos_da_descricao,
    _cobranca_de_item,
    _conta_por_ca,
    _documento_receita_item,
    _enriquecer_item_receita,
    _item_financeiro_pago,
    _nsu_receita_item,
    _params_busca_receitas,
    _parse_data,
    _parse_decimal,
)
from extrato.models import Conciliacao, ExtratoMovimento, Lancamento
from notasfiscais.models import NotaFiscalServico

CA_BAIXA_PREFIX = 'CA_BAIXA:'
CA_RECONC_PREFIX = 'CA_RECONC:'
LIMITE_DETALHE_PARCELA = 120


def _marcador_baixa(ca_baixa_id: str) -> str:
    return f'{CA_BAIXA_PREFIX}{ca_baixa_id.strip()}'


def _hash_lancamento_ca(reconc_id: str) -> str:
    return f'ca-reconc-{(reconc_id or "").strip()}'


def _numero_nf_de_item(item: dict) -> str:
    from dashboard.conta_azul.sync import _numero_fatura_item

    doc = _numero_fatura_item(item) or _documento_receita_item(item)
    if not doc:
        return ''
    m = re.search(r'(\d+)', doc)
    return m.group(1) if m else doc.strip()


def localizar_conta_a_receber(
    empresa,
    *,
    parcela_id: str,
    item_busca: dict,
    detalhe: dict,
) -> ContaAReceber | None:
    pid = (parcela_id or '').strip()
    if pid:
        car = ContaAReceber.objects.filter(empresa=empresa, conta_azul_parcela_id=pid).first()
        if car:
            return car

    merged = {**(item_busca or {}), **(detalhe or {})}
    numero_nf = _numero_nf_de_item(merged)
    if numero_nf:
        nf = (
            NotaFiscalServico.objects.filter(empresa=empresa, numero_nota=str(numero_nf))
            .order_by('-pk')
            .first()
        )
        if nf:
            car = ContaAReceber.objects.filter(empresa=empresa, nota=nf).order_by('pk').first()
            if car:
                if pid and not (car.conta_azul_parcela_id or '').strip():
                    car.conta_azul_parcela_id = pid
                    car.save(update_fields=['conta_azul_parcela_id'])
                return car

    doc = (_documento_receita_item(merged) or '').strip()
    if doc:
        car = (
            ContaAReceber.objects.filter(empresa=empresa, doc__icontains=doc[:40])
            .exclude(nota__isnull=True)
            .order_by('-pk')
            .first()
        )
        if car:
            if pid and not (car.conta_azul_parcela_id or '').strip():
                car.conta_azul_parcela_id = pid
                car.save(update_fields=['conta_azul_parcela_id'])
            return car

    return None


def _baixa_ja_importada(empresa, baixa_id: str) -> bool:
    bid = (baixa_id or '').strip()
    if not bid:
        return False
    return BaixaContaAReceber.objects.filter(
        empresa=empresa,
        observacao__contains=_marcador_baixa(bid),
    ).exists()


def _liquido_extrato_baixa(baixa: dict) -> Decimal:
    comp = baixa.get('valor_composicao') or baixa.get('composicao_valor') or {}
    if isinstance(comp, dict):
        liq = _parse_decimal(comp.get('valor_liquido'))
        if liq > 0:
            return liq
        bruto = _parse_decimal(comp.get('valor_bruto'))
        juros = _parse_decimal(comp.get('juros')) + _parse_decimal(comp.get('multa'))
        desc = _parse_decimal(comp.get('desconto'))
        calc = bruto + juros - desc
        if calc > 0:
            return calc
    return Decimal('0')


def _composicao_baixa(baixa: dict) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    comp = baixa.get('valor_composicao') or baixa.get('composicao_valor') or {}
    if not isinstance(comp, dict):
        comp = {}
    juros = _parse_decimal(comp.get('juros')) + _parse_decimal(comp.get('multa'))
    desconto = _parse_decimal(comp.get('desconto'))
    tarifa = _parse_decimal(comp.get('taxa'))
    liquido = _liquido_extrato_baixa(baixa)
    return liquido, juros, desconto, tarifa


def _baixas_conciliadas_parcela(detalhe: dict) -> list[dict]:
    out: list[dict] = []
    for baixa in detalhe.get('baixas') or []:
        if not isinstance(baixa, dict):
            continue
        if not str(baixa.get('id_reconciliacao') or '').strip():
            continue
        if str(baixa.get('tipo_evento_financeiro') or 'RECEITA').upper() == 'DESPESA':
            continue
        out.append(baixa)
    return out


def _conta_ca_da_baixa(baixa: dict, detalhe: dict) -> str:
    raw = baixa.get('conta_financeira')
    if isinstance(raw, dict):
        return str(raw.get('id') or '').strip()
    if raw:
        return str(raw).strip()
    cf = detalhe.get('conta_financeira')
    if isinstance(cf, dict):
        return str(cf.get('id') or '').strip()
    return str(detalhe.get('id_conta_financeira') or '').strip()


def _processar_baixa_conciliada(
    empresa,
    *,
    car: ContaAReceber,
    baixa: dict,
    detalhe: dict,
    item_busca: dict,
    dry_run: bool = False,
) -> str:
    baixa_id = str(baixa.get('id') or '').strip()
    reconc_id = str(baixa.get('id_reconciliacao') or '').strip()
    if not baixa_id or not reconc_id:
        return 'ignorado'

    if _baixa_ja_importada(empresa, baixa_id):
        return 'duplicado'

    conta_ca_id = _conta_ca_da_baixa(baixa, detalhe)
    conta_banco = _conta_por_ca(empresa, conta_ca_id)
    if not conta_banco:
        return 'sem_conta_banco'

    liquido, juros, desconto, tarifa = _composicao_baixa(baixa)
    if liquido <= 0:
        return 'erro'

    data_pg = _parse_data(baixa.get('data_pagamento')) or date.today()
    descricao = (
        str(baixa.get('observacao') or detalhe.get('descricao') or item_busca.get('descricao') or '')
    )[:255]
    if car.nota_id:
        nf = car.nota.numero_nota if car.nota else ''
        descricao = descricao or f'Conta Azul — NF {nf} — {car.cliente}'[:255]
    else:
        descricao = descricao or f'Conta Azul — {car.cliente}'[:255]

    hash_unico = _hash_lancamento_ca(reconc_id)
    if dry_run:
        return 'ok'

    lanc_existente = Lancamento.objects.filter(empresa=empresa, hash_unico=hash_unico).first()
    if lanc_existente and ExtratoMovimento.objects.filter(
        empresa=empresa,
        lancamento=lanc_existente,
        conta_receber=car,
    ).exists():
        return 'duplicado'

    with transaction.atomic():
        lanc, _ = Lancamento.objects.update_or_create(
            empresa=empresa,
            conta=conta_banco,
            hash_unico=hash_unico,
            defaults={
                'banco': conta_banco.banco,
                'data': data_pg,
                'documento': reconc_id[:60],
                'historico': descricao,
                'valor': liquido,
                'origem': 'CONTA_AZUL',
                'status_importacao': 'I',
                'conciliado': True,
            },
        )

        conciliacao = Conciliacao.objects.create(
            observacao=f'Conta Azul reconciliação {reconc_id}',
        )
        lanc.conciliado = True
        lanc.idconciliacao = conciliacao
        lanc.save(update_fields=['conciliado', 'idconciliacao'])

        vr_baixa = liquido - juros + desconto
        if vr_baixa <= 0:
            vr_baixa = liquido

        obs_baixa = '\n'.join(
            x
            for x in (
                _marcador_baixa(baixa_id),
                f'{CA_RECONC_PREFIX}{reconc_id}',
            )
            if x
        )
        bx = BaixaContaAReceber.objects.create(
            conta_a_receber=car,
            empresa=empresa,
            data_recebimento=data_pg,
            valor_recebido=vr_baixa,
            desconto=desconto,
            juros=juros,
            tarifas=tarifa,
            conta_banco=conta_banco,
            tipo_baixa='total',
            observacao=obs_baixa,
        )

        nsu = str(baixa.get('nsu') or _nsu_receita_item(detalhe) or '').strip()
        if nsu and not (car.autorizacao or '').strip():
            car.autorizacao = nsu[:100]
            car.save(update_fields=['autorizacao'])

        ExtratoMovimento.objects.create(
            empresa=empresa,
            data_baixa=data_pg,
            descricao=descricao,
            situacao='recebido',
            valor=liquido,
            conta_receber=car,
            baixa_receber=bx,
            lancamento=lanc,
            conta_banco=conta_banco,
            categoria=car.categoria,
        )

        if car.nota_id:
            car.nota.status_conciliacao = 'conciliado'
            car.nota.save(update_fields=['status_conciliacao'])

    return 'ok'


def importar_baixas_receitas_conciliadas_conta_azul(
    empresa,
    client: ContaAzulClient,
    *,
    data_de: date,
    data_ate: date,
    conta_banco_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        'baixas_criadas': 0,
        'lancamentos': 0,
        'ignorados_duplicados': 0,
        'ignorados_sem_titulo': 0,
        'ignorados_nao_conciliados': 0,
        'ignorados_conta': 0,
        'erros': 0,
    }

    conta_ca_filtro: set[str] = set()
    if conta_banco_id:
        from extrato.models import ContaBancaria

        cb = ContaBancaria.objects.filter(pk=conta_banco_id, empresa=empresa).first()
        if cb and (cb.conta_azul_id or '').strip():
            conta_ca_filtro.add(cb.conta_azul_id.strip())

    params = _params_busca_receitas(data_de, data_ate, por_recebimento=True)
    try:
        itens = client.buscar_receitas(**params)
    except Exception as exc:
        return {**stats, 'erro': str(exc)}

    cache_parcelas: dict[str, dict] = {}
    cache_cobranca: dict = {}
    detalhes_chamados = 0

    for item in itens:
        if not isinstance(item, dict):
            stats['erros'] += 1
            continue
        parcela_id = str(item.get('id') or item.get('id_parcela') or '').strip()
        if not parcela_id:
            stats['erros'] += 1
            continue
        item = _aplicar_campos_da_descricao(item)
        if not _item_financeiro_pago(item):
            continue

        if parcela_id not in cache_parcelas:
            if detalhes_chamados >= LIMITE_DETALHE_PARCELA:
                continue
            detalhes_chamados += 1
            item = _enriquecer_item_receita(client, item, cache_parcelas)
        detalhe = cache_parcelas.get(parcela_id) or item

        baixas = _baixas_conciliadas_parcela(detalhe)
        if not baixas:
            stats['ignorados_nao_conciliados'] += 1
            continue

        car = localizar_conta_a_receber(
            empresa,
            parcela_id=parcela_id,
            item_busca=item,
            detalhe=detalhe,
        )
        if not car:
            stats['ignorados_sem_titulo'] += 1
            continue

        if not car.forma_pagamento:
            cob = _cobranca_de_item(detalhe, cache_cobranca)
            if cob:
                car.forma_pagamento = cob
                car.save(update_fields=['forma_pagamento'])

        for baixa in baixas:
            if conta_ca_filtro:
                ca_id = _conta_ca_da_baixa(baixa, detalhe)
                if ca_id not in conta_ca_filtro:
                    stats['ignorados_conta'] += 1
                    continue

            resultado = _processar_baixa_conciliada(
                empresa,
                car=car,
                baixa=baixa,
                detalhe=detalhe,
                item_busca=item,
                dry_run=dry_run,
            )
            if resultado == 'ok':
                stats['baixas_criadas'] += 1
                stats['lancamentos'] += 1
            elif resultado == 'duplicado':
                stats['ignorados_duplicados'] += 1
            elif resultado == 'sem_conta_banco':
                stats['ignorados_conta'] += 1
            elif resultado == 'ignorado':
                stats['ignorados_nao_conciliados'] += 1
            else:
                stats['erros'] += 1

    if detalhes_chamados >= LIMITE_DETALHE_PARCELA:
        stats['detalhes_limitados'] = LIMITE_DETALHE_PARCELA

    return stats


def mensagem_resultado_baixas_ca(stats: dict[str, Any]) -> tuple[str, str]:
    if stats.get('erro'):
        return 'error', str(stats['erro'])
    partes = []
    if stats.get('baixas_criadas'):
        partes.append(f"{stats['baixas_criadas']} baixa(s) com extrato conciliado")
    if stats.get('ignorados_duplicados'):
        partes.append(f"{stats['ignorados_duplicados']} já importada(s)")
    if stats.get('ignorados_sem_titulo'):
        partes.append(f"{stats['ignorados_sem_titulo']} sem título SF (NF/conta)")
    if stats.get('ignorados_nao_conciliados'):
        partes.append(f"{stats['ignorados_nao_conciliados']} sem conciliação no CA")
    if stats.get('ignorados_conta'):
        partes.append(f"{stats['ignorados_conta']} outro banco/conta")
    if stats.get('erros'):
        partes.append(f"{stats['erros']} erro(s)")
    if stats.get('detalhes_limitados'):
        partes.append(
            f"detalhe API limitado a {stats['detalhes_limitados']} parcelas; rode de novo",
        )
    if not partes:
        return 'warning', 'Nenhuma baixa conciliada encontrada no período.'
    nivel = 'success' if stats.get('baixas_criadas') else 'warning'
    return nivel, 'Integração Conta Azul: ' + '; '.join(partes) + '.'
