"""Importação NFS-e (prestador) Conta Azul → NotaFiscalServico."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError
from django.utils.dateparse import parse_date, parse_datetime

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.venda_nfse import enriquecer_campos_nfse_com_venda_ca
from notasfiscais.models import NotaFiscalServico

CA_NFSE_ID_PREFIX = 'Conta Azul NFS-e ID:'
SERIE_PADRAO = '1'

# API CA devolve vários status; só não importamos lista explicitamente vazia de “lixo”.
STATUS_IGNORAR = frozenset()

STATUS_CA_CANCELADO = frozenset({'CANCELADA', 'CANCELAMENTO_MANUAL'})

logger = logging.getLogger(__name__)


def status_ca_cancelado(item: dict) -> bool:
    status = str(item.get('status') or '').strip().upper()
    return status in STATUS_CA_CANCELADO


def _data_cancelamento_de_item_ca(item: dict, data_emissao: date) -> date | None:
    if not status_ca_cancelado(item):
        return None
    info = item.get('informacao_transmissao') or {}
    dc_raw = info.get('data_inicio_cancelamento')
    if dc_raw:
        dt = parse_datetime(str(dc_raw)) if 'T' in str(dc_raw) else None
        if dt:
            return dt.date()
        return parse_date(str(dc_raw)[:10]) or data_emissao
    return data_emissao


def _motivo_cancelamento_de_item_ca(item: dict) -> str:
    cancel_info = item.get('informacoes_cancelamento') or {}
    return (cancel_info.get('motivo') or '').strip()[:500]


def aplicar_regras_nfse_cancelada_ca(
    nfse: NotaFiscalServico,
    *,
    data_cancelamento: date | None,
    motivo: str,
) -> None:
    """Mesma regra do evento/XML: data de cancelamento, motivo e valores zerados."""
    from notasfiscais.nfse_evento_cancelamento import aplicar_cancelamento_por_evento

    aplicar_cancelamento_por_evento(
        nfse,
        data_cancelamento=data_cancelamento,
        codigo_motivo='',
        motivo=motivo,
    )


def _marcador_ca_id(ca_id: str) -> str:
    return f'{CA_NFSE_ID_PREFIX} {ca_id.strip()}'


def _numero_nfse_de_item(item: dict) -> int | None:
    for key in ('numero_nfse', 'numeroNfse', 'numero'):
        raw = item.get(key)
        if raw is None or raw == '':
            continue
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            continue
    return None


def _parse_data_item(item: dict) -> date | None:
    info = item.get('informacao_transmissao') or {}
    for raw in (info.get('data_inicio_emissao'), item.get('data_competencia')):
        if not raw:
            continue
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        s = str(raw).strip()
        if len(s) >= 10 and s[4] == '-':
            d = parse_date(s[:10])
            if d:
                return d
        if 'T' in s:
            dt = parse_datetime(s)
            if dt:
                return dt.date()
        if len(s) == 7 and s[4] == '-':
            d = parse_date(f'{s}-01')
            if d:
                return d
    return None


def _documento_cliente(raw: str) -> str:
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 14:
        return f'{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}'
    if len(digits) == 11:
        return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
    return (raw or '')[:18]


def _decimal_valor(raw: Any) -> Decimal:
    if raw is None or raw == '':
        return Decimal('0')
    try:
        return Decimal(str(raw).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _ca_id_em_observacoes(observacoes: str | None) -> str:
    if not observacoes:
        return ''
    m = re.search(rf'{re.escape(CA_NFSE_ID_PREFIX)}\s*(\S+)', observacoes)
    return (m.group(1).strip() if m else '')


def _localizar_nfse(empresa, ca_id: str, numero_nota: str, serie: str) -> NotaFiscalServico | None:
    if ca_id:
        marcador = _marcador_ca_id(ca_id)
        obj = (
            NotaFiscalServico.objects.filter(empresa=empresa, observacoes__contains=marcador)
            .order_by('-pk')
            .first()
        )
        if obj:
            return obj
    for obj in (
        NotaFiscalServico.objects.filter(
            empresa=empresa,
            numero_nota=numero_nota,
            serie=serie,
        )
        .order_by('-pk')
    ):
        ca_existente = _ca_id_em_observacoes(obj.observacoes)
        if ca_existente and ca_id and ca_existente != ca_id:
            continue
        return obj
    return None


def _campos_de_item_ca(item: dict, *, empresa) -> dict[str, Any] | None:
    ca_id = str(item.get('id') or '').strip()
    numero_int = _numero_nfse_de_item(item)
    if numero_int is None:
        return None
    numero_nota = str(numero_int).strip()
    if not numero_nota:
        return None

    status = str(item.get('status') or '').strip().upper()
    if status and status in STATUS_IGNORAR:
        return None

    data_emissao = _parse_data_item(item) or date.today()
    valor = _decimal_valor(item.get('valor_total_nfse'))
    nome_cliente = (item.get('nome_cliente') or 'Cliente não informado').strip()[:200]
    doc = _documento_cliente(str(item.get('documento_cliente') or ''))

    motivo_cancel = _motivo_cancelamento_de_item_ca(item)
    data_cancelamento = _data_cancelamento_de_item_ca(item, data_emissao)

    numero_rps = item.get('numero_rps')
    meta_ca: list[str] = []
    if numero_rps is not None:
        meta_ca.append(f'RPS {numero_rps}')
    if item.get('numero_venda'):
        meta_ca.append(f'Venda {item.get("numero_venda")}')
    if item.get('codigo_cnae'):
        meta_ca.append(f'CNAE {item.get("codigo_cnae")}')

    obs_lines = [
        _marcador_ca_id(ca_id) if ca_id else '',
        f'Status Conta Azul: {status or "—"}',
    ]
    if meta_ca:
        obs_lines.append(' — '.join(meta_ca))
    if item.get('id_venda'):
        obs_lines.append(f'id_venda: {item.get("id_venda")}')
    observacoes = '\n'.join(x for x in obs_lines if x)

    valor_gravacao = valor
    if status_ca_cancelado(item):
        valor_gravacao = Decimal('0')

    campos: dict[str, Any] = {
        'numero_nota': numero_nota,
        'serie': SERIE_PADRAO,
        'numero_dps': str(numero_rps).strip() if numero_rps is not None else None,
        'data_emissao': data_emissao,
        'cnpj_cpf': doc or '—',
        'cliente': nome_cliente,
        'valor_bruto': valor_gravacao,
        'valor_liquido': valor_gravacao,
        'data_cancelamento': data_cancelamento,
        'motivo_cancelamento': motivo_cancel,
        'observacoes': observacoes,
    }

    return campos


def _janelas_competencia_15_dias(data_de: date, data_ate: date):
    cur = data_de
    while cur <= data_ate:
        fim = min(cur + timedelta(days=14), data_ate)
        yield cur, fim
        cur = fim + timedelta(days=1)


MAX_JANELAS_VARREDURA_WEB = 24
TEMPO_MAX_VARREDURA_WEB_S = 28.0


def _janelas_varredura_numero_global(
    *,
    dias_retro: int = 450,
    dias_frente: int = 30,
    recentes_primeiro: bool = True,
):
    """Janelas de 15 dias; por padrão das mais recentes para as antigas (achar NF logo)."""
    hoje = date.today()
    inicio = hoje - timedelta(days=dias_retro)
    fim = hoje + timedelta(days=dias_frente)
    janelas = list(_janelas_competencia_15_dias(inicio, fim))
    if recentes_primeiro:
        janelas = list(reversed(janelas))
    yield from janelas


def _nf_numero_existe_local(empresa, numero: int) -> bool:
    from contasareceber.nf_sync_discriminacao import _variantes_numero_nf

    chaves = _variantes_numero_nf(str(numero))
    if not chaves:
        return False
    return NotaFiscalServico.objects.filter(empresa=empresa, numero_nota__in=chaves).exists()


def importar_nfse_prestador_conta_azul(
    empresa,
    client: ContaAzulClient,
    *,
    data_de: date,
    data_ate: date,
    dry_run: bool = False,
    numero_nfse: int | None = None,
    varredura_profunda: bool = False,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        'criados': 0,
        'atualizados': 0,
        'erros': 0,
        'ignorados_status': 0,
        'ignorados_sem_numero': 0,
        'vendas_sincronizadas': 0,
        'canceladas_aplicadas': 0,
        'car_vinculados': 0,
    }
    vistos: set[str] = set()
    cache_vendas: dict[str, dict] = {}
    cache_cobranca: dict = {}

    def _busca_kw() -> dict[str, int]:
        if numero_nfse is None:
            return {}
        return {
            'numero_nfse_inicial': int(numero_nfse),
            'numero_nfse_final': int(numero_nfse),
        }

    def _processar_itens(itens: list) -> None:
        nonlocal stats
        for item in itens:
            if not isinstance(item, dict):
                stats['erros'] += 1
                continue
            if numero_nfse is not None:
                n_item = _numero_nfse_de_item(item)
                if n_item is not None and n_item != numero_nfse:
                    continue
            ca_id = str(item.get('id') or '').strip()
            if ca_id:
                if ca_id in vistos:
                    continue
                vistos.add(ca_id)

            campos = _campos_de_item_ca(item, empresa=empresa)
            if campos is None:
                if _numero_nfse_de_item(item) is None:
                    stats['ignorados_sem_numero'] += 1
                else:
                    stats['ignorados_status'] += 1
                continue

            if dry_run:
                stats['criados'] += 1
                continue

            if item.get('id_venda') and not status_ca_cancelado(item):
                antes = (campos.get('discriminacao') or '').strip()
                enriquecer_campos_nfse_com_venda_ca(
                    client,
                    item,
                    campos,
                    empresa_id=empresa.pk,
                    cache_vendas=cache_vendas,
                    cache_cobranca=cache_cobranca,
                )
                depois = (campos.get('discriminacao') or '').strip()
                if (
                    (depois and depois != antes)
                    or campos.get('forma_pagamento') is not None
                    or (campos.get('caixa_acerto_sugerido') or '').strip()
                ):
                    stats['vendas_sincronizadas'] += 1

            existente = _localizar_nfse(
                empresa,
                ca_id,
                campos['numero_nota'],
                campos['serie'],
            )
            try:
                from contasareceber.nf_sync_discriminacao import vincular_contas_receber_a_nota_por_doc

                cancelamento_ca = status_ca_cancelado(item)
                if existente:
                    from notasfiscais.discriminacao_nfse import (
                        discriminacao_e_resumo_placeholder_ca,
                        discriminacao_valor_coerente,
                    )

                    ja_cancelada = existente.is_cancelada()
                    valor_ca = campos.get('valor_liquido') or campos.get('valor_bruto')
                    disc_incoerente = not discriminacao_valor_coerente(
                        existente.discriminacao,
                        valor_ca,
                    )
                    for k, v in campos.items():
                        if k in ('data_cancelamento', 'motivo_cancelamento'):
                            continue
                        if k == 'discriminacao':
                            nova = (v or '').strip()
                            if disc_incoerente and nova:
                                setattr(existente, k, v)
                                existente.forma_pagamento = None
                                existente.nsu = ''
                            elif nova and not (existente.discriminacao or '').strip():
                                setattr(existente, k, v)
                            elif nova and discriminacao_e_resumo_placeholder_ca(
                                existente.discriminacao or '',
                            ):
                                setattr(existente, k, v)
                            elif nova and 'PAGAMENTO' in nova.upper() and 'PAGAMENTO' not in (
                                existente.discriminacao or ''
                            ).upper():
                                setattr(existente, k, v)
                            continue
                        if k == 'forma_pagamento' and v is not None:
                            setattr(existente, k, v)
                            continue
                        if k == 'caixa_acerto_sugerido' and v:
                            if not (existente.caixa_acerto_sugerido or '').strip():
                                setattr(existente, k, v)
                            continue
                        if k == 'nsu' and v and not (existente.nsu or '').strip():
                            setattr(existente, k, v)
                            continue
                        if k in ('valor_bruto', 'valor_liquido') and cancelamento_ca:
                            continue
                        setattr(existente, k, v)
                    if cancelamento_ca:
                        aplicar_regras_nfse_cancelada_ca(
                            existente,
                            data_cancelamento=campos.get('data_cancelamento'),
                            motivo=campos.get('motivo_cancelamento') or '',
                        )
                        if not ja_cancelada:
                            stats['canceladas_aplicadas'] += 1
                    existente.save()
                    stats['atualizados'] += 1
                    stats['car_vinculados'] += vincular_contas_receber_a_nota_por_doc(existente)
                else:
                    nf = NotaFiscalServico.objects.create(empresa=empresa, **campos)
                    if cancelamento_ca:
                        aplicar_regras_nfse_cancelada_ca(
                            nf,
                            data_cancelamento=campos.get('data_cancelamento'),
                            motivo=campos.get('motivo_cancelamento') or '',
                        )
                        nf.save()
                        stats['canceladas_aplicadas'] += 1
                    stats['criados'] += 1
                    stats['car_vinculados'] += vincular_contas_receber_a_nota_por_doc(nf)
            except IntegrityError:
                stats['erros'] += 1
            except Exception as exc:
                logger.exception(
                    'Falha ao gravar NFS-e CA (empresa=%s numero=%s id=%s): %s',
                    empresa.pk,
                    campos.get('numero_nota'),
                    ca_id,
                    exc,
                )
                stats['erros'] += 1

    kw = _busca_kw()
    for cur, fim in _janelas_competencia_15_dias(data_de, data_ate):
        try:
            itens = client.buscar_notas_fiscais_servico(data_de=cur, data_ate=fim, **kw)
        except ContaAzulAPIError as exc:
            return {**stats, 'erro': f'{cur.isoformat()} a {fim.isoformat()}: {exc}'}
        _processar_itens(itens)

    if numero_nfse is not None and not dry_run and not _nf_numero_existe_local(empresa, numero_nfse):
        retro = 900 if varredura_profunda else 450
        limite_janelas = 120 if varredura_profunda else MAX_JANELAS_VARREDURA_WEB
        tempo_limite = 180.0 if varredura_profunda else TEMPO_MAX_VARREDURA_WEB_S
        t0 = time.monotonic()
        stats['busca_numero_ampla'] = 0
        for cur, fim in _janelas_varredura_numero_global(dias_retro=retro):
            if time.monotonic() - t0 > tempo_limite:
                stats['busca_ampliada_interrompida'] = True
                stats['busca_motivo'] = 'tempo'
                break
            if stats['busca_numero_ampla'] >= limite_janelas:
                stats['busca_ampliada_interrompida'] = True
                stats['busca_motivo'] = 'limite_janelas'
                break
            try:
                itens = client.buscar_notas_fiscais_servico(
                    data_de=cur,
                    data_ate=fim,
                    numero_nfse_inicial=numero_nfse,
                    numero_nfse_final=numero_nfse,
                )
            except ContaAzulAPIError:
                continue
            _processar_itens(itens)
            stats['busca_numero_ampla'] += 1
            if _nf_numero_existe_local(empresa, numero_nfse):
                break

    if numero_nfse is not None and not _nf_numero_existe_local(empresa, numero_nfse):
        stats['numero_nao_encontrado'] = numero_nfse

    return stats
