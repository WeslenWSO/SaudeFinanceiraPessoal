"""Conciliação extrato SF × contexto Conta Azul (sugestões e divergências)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber
from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.resumo import _annotate_conciliado_pagar, _annotate_conciliado_receber
from dashboard.conta_azul.sync import (
    _item_financeiro_pago,
    _map_status_despesa,
    _map_status_receita,
    _valor_pago_item,
)
from extrato.models import ContaBancaria, Lancamento
from extrato.services.stone_conciliacao_previa import (
    eh_lancamento_stone,
    sugerir_conciliacao_stone,
)
from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

TOLERANCIA_VALOR = Decimal('0.10')
TOLERANCIA_VALOR_TITULO = Decimal('0.05')
JANELA_VENCIMENTO_DIAS = 3
JANELA_VENCIMENTO_LISTAGEM_DIAS = 14
JANELA_RECEBIVEL_DIAS = 3
SCORE_MINIMO_LISTAGEM = 5

TipoSugestao = Literal['receber', 'pagar', 'cartao']


@dataclass
class SugestaoConciliacao:
    tipo: TipoSugestao
    pk: int
    score: int
    valor: Decimal
    rotulo: str
    detalhe: str
    sync_ca: bool
    baixado_ca: bool
    conciliado_extrato: bool
    meta: dict[str, Any] = field(default_factory=dict)


def contas_bancarias_conciliacao(empresa) -> list[ContaBancaria]:
    return list(
        ContaBancaria.objects.filter(empresa=empresa, status='A')
        .select_related('banco')
        .order_by('-conta_azul_id', 'descricao')
    )


def montar_resumo_conta(conta: ContaBancaria | None, *, pendentes_qs) -> dict[str, Any]:
    total_pendente = pendentes_qs.aggregate(t=Coalesce(Sum('valor'), Decimal('0')))['t'] or Decimal('0')
    receb_qs = pendentes_qs.filter(valor__gt=0)
    pag_qs = pendentes_qs.filter(valor__lt=0)
    total_receb = receb_qs.aggregate(t=Coalesce(Sum('valor'), Decimal('0')))['t'] or Decimal('0')
    total_pag = pag_qs.aggregate(t=Coalesce(Sum('valor'), Decimal('0')))['t'] or Decimal('0')
    saldo_ca = (conta.saldo_conta_azul if conta else None) or Decimal('0')
    return {
        'total_pendente': abs(total_pendente),
        'qtd_pendentes': pendentes_qs.count(),
        'qtd_recebimentos': receb_qs.count(),
        'qtd_pagamentos': pag_qs.count(),
        'total_recebimentos': total_receb,
        'total_pagamentos': abs(total_pag),
        'saldo_conta_azul': saldo_ca,
        'saldo_conta_azul_em': conta.saldo_conta_azul_em if conta else None,
    }


def _tokens_busca(texto: str) -> list[str]:
    if not texto:
        return []
    nums = re.findall(r'\d{3,}', texto)
    palavras = re.findall(r'[A-Za-zÀ-ÿ]{4,}', texto or '')
    tokens = []
    for n in nums:
        if n not in tokens:
            tokens.append(n)
    for p in palavras[:5]:
        pl = p.lower()
        if pl not in ('recebimento', 'vendas', 'credito', 'debito', 'mastercard', 'stone'):
            tokens.append(pl)
    return tokens[:8]


def _score_valor(valor_lanc: Decimal, valor_titulo: Decimal) -> int:
    diff = abs(abs(valor_lanc) - valor_titulo)
    if diff <= Decimal('0.01'):
        return 40
    if diff <= TOLERANCIA_VALOR_TITULO:
        return 30
    if diff <= TOLERANCIA_VALOR:
        return 15
    return 0


def _score_texto(tokens: list[str], *campos: str) -> int:
    if not tokens:
        return 0
    blob = ' '.join((c or '') for c in campos).lower()
    pts = 0
    for t in tokens:
        if t.lower() in blob:
            pts += 25
    return min(pts, 50)


def sugerir_recebiveis_cartao(lancamento: Lancamento) -> list[SugestaoConciliacao]:
    sugestoes: list[SugestaoConciliacao] = []
    if lancamento.valor <= 0 or lancamento.conciliado:
        return sugestoes

    stone = sugerir_conciliacao_stone(lancamento, lancamento.empresa_id)
    if stone and stone.get('itens'):
        for item in stone['itens']:
            sugestoes.append(
                SugestaoConciliacao(
                    tipo='cartao',
                    pk=int(item['id']),
                    score=80 if stone.get('confianca') == 'alta' else 55,
                    valor=Decimal(str(item['valor_liquido'])),
                    rotulo=f"Stone {item.get('bandeira', '')} {item.get('parcela', '')}",
                    detalhe=f"NF {item.get('nota_fiscal', '')} — {item.get('cliente', '')}"[:120],
                    sync_ca=False,
                    baixado_ca=False,
                    conciliado_extrato=False,
                    meta={'relatorio_ids': stone.get('relatorio_ids') or []},
                )
            )

    if not lancamento.data:
        return sugestoes
    data_ini = lancamento.data - timedelta(days=JANELA_RECEBIVEL_DIAS)
    data_fim = lancamento.data + timedelta(days=JANELA_RECEBIVEL_DIAS)
    alvo = abs(lancamento.valor)
    for rel in RelatorioRecebiveisMaquinaCartao.objects.filter(
        empresa_id=lancamento.empresa_id,
        conciliado=False,
        data_pagamento__range=(data_ini, data_fim),
    ).order_by('data_pagamento')[:40]:
        sc = _score_valor(alvo, rel.valor_liquido)
        if sc <= 0:
            continue
        sugestoes.append(
            SugestaoConciliacao(
                tipo='cartao',
                pk=rel.pk,
                score=sc + 10,
                valor=rel.valor_liquido,
                rotulo=f"{rel.maquinha} {rel.bandeira} {rel.parcelas}/{rel.total_parcelas}",
                detalhe=(rel.razao or rel.nota_fiscal or '')[:120],
                sync_ca=False,
                baixado_ca=False,
                conciliado_extrato=False,
            )
        )
    return sorted(sugestoes, key=lambda s: -s.score)[:15]


def _janela_vencimento_titulos(
    lancamento: Lancamento,
    periodo_de: date | None,
    periodo_ate: date | None,
) -> tuple[date, date]:
    """Usa o período da tela; expande em torno da data do lançamento."""
    if periodo_de and periodo_ate:
        base_ini, base_fim = periodo_de, periodo_ate
    elif lancamento.data:
        base_ini = base_fim = lancamento.data
    else:
        hoje = date.today()
        base_ini = date(hoje.year, hoje.month, 1)
        base_fim = base_ini

    if lancamento.data:
        base_ini = min(base_ini, lancamento.data - timedelta(days=JANELA_VENCIMENTO_LISTAGEM_DIAS))
        base_fim = max(base_fim, lancamento.data + timedelta(days=JANELA_VENCIMENTO_LISTAGEM_DIAS))
    return base_ini, base_fim


def sugerir_titulos_para_lancamento(
    lancamento: Lancamento,
    *,
    busca: str = '',
    periodo_de: date | None = None,
    periodo_ate: date | None = None,
) -> list[SugestaoConciliacao]:
    if lancamento.conciliado:
        return []

    empresa_id = lancamento.empresa_id
    tokens = _tokens_busca(busca or lancamento.historico or '')
    alvo = abs(lancamento.valor)
    credito = lancamento.valor > 0
    sugestoes: list[SugestaoConciliacao] = []

    dv_ini, dv_fim = _janela_vencimento_titulos(lancamento, periodo_de, periodo_ate)

    if credito:
        qs = _annotate_conciliado_receber(
            ContaAReceber.objects.filter(
                empresa_id=empresa_id,
                status__in=('pendente', 'vencido', 'cartao'),
                data_vencimento__gte=dv_ini,
                data_vencimento__lte=dv_fim,
            )
        )
        if busca:
            qs = qs.filter(
                Q(cliente__icontains=busca)
                | Q(doc__icontains=busca)
                | Q(observacao__icontains=busca)
                | Q(parcela__icontains=busca)
            )
        qs = qs.select_related('nota')[:80]

        for car in qs:
            sc = _score_valor(alvo, car.valor_a_receber)
            sc += _score_texto(tokens, car.doc or '', car.observacao or '', car.cliente or '')
            if car.conta_azul_parcela_id:
                sc += 5
            if lancamento.data:
                dias = abs((car.data_vencimento - lancamento.data).days)
                if dias <= JANELA_VENCIMENTO_DIAS:
                    sc += 20
                elif dias <= JANELA_VENCIMENTO_LISTAGEM_DIAS:
                    sc += 8
            baixado_ca = car.status == 'pago' or bool(car.data_recebimento)
            if sc < SCORE_MINIMO_LISTAGEM:
                sc = SCORE_MINIMO_LISTAGEM
            if busca and sc < 15:
                sc = max(sc, 20)
            nf = ''
            if car.nota_id:
                nf = str(car.nota.numero_nota or '')
            sugestoes.append(
                SugestaoConciliacao(
                    tipo='receber',
                    pk=car.pk,
                    score=sc,
                    valor=car.valor_a_receber,
                    rotulo=f"{car.parcela} — {car.cliente}"[:80],
                    detalhe=f"Doc {car.doc or nf} — venc. {car.data_vencimento:%d/%m/%Y}",
                    sync_ca=bool((car.conta_azul_parcela_id or '').strip()),
                    baixado_ca=baixado_ca,
                    conciliado_extrato=getattr(car, 'conciliado_extrato', False),
                )
            )
    else:
        qs = _annotate_conciliado_pagar(
            ContasaPagar.objects.filter(
                empresa_id=empresa_id,
                status='pendente',
                dtvenc__gte=dv_ini,
                dtvenc__lte=dv_fim,
            )
        )
        if busca:
            qs = qs.filter(
                Q(descricao__icontains=busca)
                | Q(numdoc__icontains=busca)
                | Q(fornecedor__razao__icontains=busca)
            )
        qs = qs.select_related('fornecedor')[:80]

        for cap in qs:
            sc = _score_valor(alvo, cap.valorDoc)
            sc += _score_texto(tokens, cap.descricao or '', cap.numdoc or '')
            if cap.conta_azul_parcela_id:
                sc += 5
            if lancamento.data:
                dias = abs((cap.dtvenc - lancamento.data).days)
                if dias <= JANELA_VENCIMENTO_DIAS:
                    sc += 20
                elif dias <= JANELA_VENCIMENTO_LISTAGEM_DIAS:
                    sc += 8
            baixado_ca = cap.status == 'pago' or bool(cap.dtPag)
            if sc < SCORE_MINIMO_LISTAGEM:
                sc = SCORE_MINIMO_LISTAGEM
            forn = cap.fornecedor.razao if cap.fornecedor_id else ''
            sugestoes.append(
                SugestaoConciliacao(
                    tipo='pagar',
                    pk=cap.pk,
                    score=sc,
                    valor=cap.valorDoc,
                    rotulo=(cap.descricao or forn or cap.numdoc or '')[:80],
                    detalhe=f"Venc. {cap.dtvenc:%d/%m/%Y} — R$ {cap.valorDoc}",
                    sync_ca=bool((cap.conta_azul_parcela_id or '').strip()),
                    baixado_ca=baixado_ca,
                    conciliado_extrato=getattr(cap, 'conciliado_extrato', False),
                )
            )

    cartao = sugerir_recebiveis_cartao(lancamento)
    for s in cartao:
        sugestoes.append(s)

    return sorted(sugestoes, key=lambda s: (-s.score, s.valor))[:25]


def montar_fila_lancamentos(
    empresa,
    *,
    conta_id: int | None,
    data_de: date,
    data_ate: date,
    aba: str = 'pendentes',
    tipo_movimento: str = 'todos',
) -> list[Lancamento]:
    qs = Lancamento.objects.filter(
        empresa=empresa,
        data__gte=data_de,
        data__lte=data_ate,
    ).select_related('conta', 'conta__banco')
    if conta_id:
        qs = qs.filter(conta_id=conta_id)
    if aba == 'conciliados':
        qs = qs.filter(conciliado=True)
    else:
        qs = qs.filter(conciliado=False)
    tipo_movimento = (tipo_movimento or 'todos').lower()
    if tipo_movimento == 'recebimentos':
        qs = qs.filter(valor__gt=0)
    elif tipo_movimento == 'pagamentos':
        qs = qs.filter(valor__lt=0)
    return list(qs.order_by('-data', '-id')[:200])


def lancamento_eh_cartao_destaque(lancamento: Lancamento) -> bool:
    return eh_lancamento_stone(lancamento)


def serializar_sugestao(s: SugestaoConciliacao) -> dict[str, Any]:
    return {
        'tipo': s.tipo,
        'pk': s.pk,
        'score': s.score,
        'valor': s.valor,
        'rotulo': s.rotulo,
        'detalhe': s.detalhe,
        'sync_ca': s.sync_ca,
        'baixado_ca': s.baixado_ca,
        'conciliado_extrato': s.conciliado_extrato,
        'meta': s.meta,
    }


def _mapa_receitas_sf(empresa, data_de: date, data_ate: date) -> dict[str, dict]:
    qs = ContaAReceber.objects.filter(
        empresa=empresa,
        conta_azul_parcela_id__gt='',
        data_vencimento__gte=data_de,
        data_vencimento__lte=data_ate,
    )
    mapa: dict[str, dict] = {}
    for c in qs:
        mapa[c.conta_azul_parcela_id] = {
            'valor': c.valor_recebido if c.status == 'pago' and c.valor_recebido else c.valor_a_receber,
            'status': c.status,
            'desc': (c.cliente or '')[:70],
            'data': c.data_recebimento or c.data_vencimento,
        }
    return mapa


def _mapa_despesas_sf(empresa, data_de: date, data_ate: date) -> dict[str, dict]:
    qs = ContasaPagar.objects.filter(
        empresa=empresa,
        conta_azul_parcela_id__gt='',
        dtvenc__gte=data_de,
        dtvenc__lte=data_ate,
    )
    mapa: dict[str, dict] = {}
    for c in qs:
        mapa[c.conta_azul_parcela_id] = {
            'valor': c.valorPago if c.status == 'pago' and c.valorPago else c.valorDoc,
            'status': c.status,
            'desc': (c.descricao or '')[:70],
            'data': c.dtPag or c.dtvenc,
        }
    return mapa


def _mapa_receitas_ca(client: ContaAzulClient, data_de: date, data_ate: date) -> dict[str, dict]:
    params = {
        'data_vencimento_de': data_de.isoformat(),
        'data_vencimento_ate': data_ate.isoformat(),
    }
    itens = client.buscar_receitas(**params)
    mapa: dict[str, dict] = {}
    for it in itens:
        pid = str(it.get('id') or it.get('id_parcela') or '').strip()
        if not pid:
            continue
        mapa[pid] = {
            'valor': _valor_pago_item(it) if _item_financeiro_pago(it) else _valor_pago_item(it),
            'status': _map_status_receita(it),
            'desc': (it.get('descricao') or '')[:70],
            'pago': _item_financeiro_pago(it),
        }
        if mapa[pid]['valor'] <= 0:
            vb = it.get('valor') or it.get('total') or it.get('valor_original')
            try:
                mapa[pid]['valor'] = Decimal(str(vb))
            except Exception:
                pass
    return mapa


def _mapa_despesas_ca(client: ContaAzulClient, data_de: date, data_ate: date) -> dict[str, dict]:
    params = {
        'data_vencimento_de': data_de.isoformat(),
        'data_vencimento_ate': data_ate.isoformat(),
    }
    itens = client.buscar_despesas(**params)
    mapa: dict[str, dict] = {}
    for it in itens:
        pid = str(it.get('id') or it.get('id_parcela') or '').strip()
        if not pid:
            continue
        mapa[pid] = {
            'valor': _valor_pago_item(it),
            'status': _map_status_despesa(it),
            'desc': (it.get('descricao') or '')[:70],
            'pago': _item_financeiro_pago(it),
        }
    return mapa


def _diff_mapas(
    titulo: str,
    ca: dict[str, dict],
    sf: dict[str, dict],
) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    ca_ids = set(ca.keys())
    sf_ids = set(sf.keys())
    for pid in sorted(ca_ids - sf_ids):
        linhas.append({
            'tipo_titulo': titulo,
            'parcela_id': pid,
            'motivo': 'so_ca',
            'valor_ca': ca[pid]['valor'],
            'valor_sf': None,
            'descricao': ca[pid]['desc'],
        })
    for pid in sorted(sf_ids - ca_ids):
        linhas.append({
            'tipo_titulo': titulo,
            'parcela_id': pid,
            'motivo': 'so_sf',
            'valor_ca': None,
            'valor_sf': sf[pid]['valor'],
            'descricao': sf[pid]['desc'],
        })
    for pid in sorted(ca_ids & sf_ids):
        dv = ca[pid]['valor'] - sf[pid]['valor']
        st_ca = ca[pid].get('status')
        st_sf = sf[pid].get('status')
        if abs(dv) > Decimal('0.01'):
            linhas.append({
                'tipo_titulo': titulo,
                'parcela_id': pid,
                'motivo': 'valor_diferente',
                'valor_ca': ca[pid]['valor'],
                'valor_sf': sf[pid]['valor'],
                'descricao': sf[pid]['desc'] or ca[pid]['desc'],
                'diferenca': dv,
            })
        elif st_ca != st_sf and (ca[pid].get('pago') or st_sf == 'pago'):
            linhas.append({
                'tipo_titulo': titulo,
                'parcela_id': pid,
                'motivo': 'status_diferente',
                'valor_ca': ca[pid]['valor'],
                'valor_sf': sf[pid]['valor'],
                'descricao': sf[pid]['desc'],
                'status_ca': st_ca,
                'status_sf': st_sf,
            })
    return linhas


def montar_divergencias_ca(
    empresa,
    client: ContaAzulClient,
    data_de: date,
    data_ate: date,
) -> dict[str, Any]:
    try:
        ca_rec = _mapa_receitas_ca(client, data_de, data_ate)
        ca_desp = _mapa_despesas_ca(client, data_de, data_ate)
    except ContaAzulAPIError as exc:
        return {'erro': str(exc), 'linhas': []}

    sf_rec = _mapa_receitas_sf(empresa, data_de, data_ate)
    sf_desp = _mapa_despesas_sf(empresa, data_de, data_ate)

    linhas = _diff_mapas('Receita', ca_rec, sf_rec) + _diff_mapas('Despesa', ca_desp, sf_desp)
    linhas.sort(key=lambda x: abs(x.get('diferenca') or Decimal('0')), reverse=True)
    return {
        'erro': None,
        'linhas': linhas[:100],
        'totais': {
            'ca_receitas': len(ca_rec),
            'sf_receitas': len(sf_rec),
            'ca_despesas': len(ca_desp),
            'sf_despesas': len(sf_desp),
        },
    }
