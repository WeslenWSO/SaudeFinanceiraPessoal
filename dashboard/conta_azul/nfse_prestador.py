"""Importação NFS-e (prestador) Conta Azul → NotaFiscalServico."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError
from django.utils.dateparse import parse_date, parse_datetime

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.venda_nfse import enriquecer_campos_nfse_com_venda_ca
from notasfiscais.models import NotaFiscalServico
from notasfiscais.utils import extrair_socio
from socio.models import Socio

CA_NFSE_ID_PREFIX = 'Conta Azul NFS-e ID:'
SERIE_PADRAO = '1'

STATUS_IMPORTAR = frozenset(
    {
        'EMITIDA',
        'CORRIGIDA_SUCESSO',
        'CANCELADA',
        'CANCELAMENTO_MANUAL',
    }
)


def _marcador_ca_id(ca_id: str) -> str:
    return f'{CA_NFSE_ID_PREFIX} {ca_id.strip()}'


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
    numero = item.get('numero_nfse')
    if numero is None:
        return None
    numero_nota = str(numero).strip()
    if not numero_nota:
        return None

    status = str(item.get('status') or '').strip().upper()
    if status and status not in STATUS_IMPORTAR:
        return None

    data_emissao = _parse_data_item(item) or date.today()
    valor = _decimal_valor(item.get('valor_total_nfse'))
    nome_cliente = (item.get('nome_cliente') or 'Cliente não informado').strip()[:200]
    doc = _documento_cliente(str(item.get('documento_cliente') or ''))

    cancel_info = item.get('informacoes_cancelamento') or {}
    motivo_cancel = (cancel_info.get('motivo') or '').strip()
    data_cancelamento = None
    if status in ('CANCELADA', 'CANCELAMENTO_MANUAL'):
        info = item.get('informacao_transmissao') or {}
        dc_raw = info.get('data_inicio_cancelamento')
        if dc_raw:
            dt = parse_datetime(str(dc_raw)) if 'T' in str(dc_raw) else None
            if dt:
                data_cancelamento = dt.date()
            else:
                data_cancelamento = parse_date(str(dc_raw)[:10]) or data_emissao
        else:
            data_cancelamento = data_emissao

    numero_rps = item.get('numero_rps')
    discriminacao_parts = []
    if numero_rps is not None:
        discriminacao_parts.append(f'RPS {numero_rps}')
    if item.get('numero_venda'):
        discriminacao_parts.append(f'Venda {item.get("numero_venda")}')
    if item.get('codigo_cnae'):
        discriminacao_parts.append(f'CNAE {item.get("codigo_cnae")}')
    discriminacao = ' — '.join(discriminacao_parts) if discriminacao_parts else ''

    obs_lines = [
        _marcador_ca_id(ca_id) if ca_id else '',
        f'Status Conta Azul: {status or "—"}',
    ]
    if item.get('id_venda'):
        obs_lines.append(f'id_venda: {item.get("id_venda")}')
    observacoes = '\n'.join(x for x in obs_lines if x)

    campos: dict[str, Any] = {
        'numero_nota': numero_nota,
        'serie': SERIE_PADRAO,
        'numero_dps': str(numero_rps).strip() if numero_rps is not None else None,
        'data_emissao': data_emissao,
        'cnpj_cpf': doc or '—',
        'cliente': nome_cliente,
        'valor_bruto': valor,
        'valor_liquido': valor,
        'data_cancelamento': data_cancelamento,
        'motivo_cancelamento': motivo_cancel[:500] if motivo_cancel else '',
        'observacoes': observacoes,
    }
    if discriminacao and not campos.get('discriminacao'):
        campos['discriminacao'] = discriminacao

    if getattr(empresa, 'pk', None) and discriminacao:
        socio = extrair_socio(discriminacao, Socio.objects.filter(empresa=empresa))
        if socio:
            campos['socio'] = socio

    return campos


def importar_nfse_prestador_conta_azul(
    empresa,
    client: ContaAzulClient,
    *,
    data_de: date,
    data_ate: date,
    dry_run: bool = False,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        'criados': 0,
        'atualizados': 0,
        'erros': 0,
        'ignorados_status': 0,
        'ignorados_sem_numero': 0,
        'vendas_sincronizadas': 0,
    }
    vistos: set[str] = set()
    cache_vendas: dict[str, dict] = {}
    cache_cobranca: dict = {}
    cur = data_de
    while cur <= data_ate:
        fim = min(cur + timedelta(days=14), data_ate)
        try:
            itens = client.buscar_notas_fiscais_servico(data_de=cur, data_ate=fim)
        except ContaAzulAPIError as exc:
            return {**stats, 'erro': f'{cur.isoformat()} a {fim.isoformat()}: {exc}'}
        for item in itens:
            if not isinstance(item, dict):
                stats['erros'] += 1
                continue
            ca_id = str(item.get('id') or '').strip()
            if ca_id:
                if ca_id in vistos:
                    continue
                vistos.add(ca_id)

            campos = _campos_de_item_ca(item, empresa=empresa)
            if campos is None:
                if item.get('numero_nfse') is None:
                    stats['ignorados_sem_numero'] += 1
                else:
                    stats['ignorados_status'] += 1
                continue

            if dry_run:
                stats['criados'] += 1
                continue

            if item.get('id_venda'):
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
                if depois and depois != antes:
                    stats['vendas_sincronizadas'] += 1

            existente = _localizar_nfse(
                empresa,
                ca_id,
                campos['numero_nota'],
                campos['serie'],
            )
            try:
                if existente:
                    from notasfiscais.discriminacao_nfse import discriminacao_valor_coerente

                    valor_ca = campos.get('valor_liquido') or campos.get('valor_bruto')
                    disc_incoerente = not discriminacao_valor_coerente(
                        existente.discriminacao,
                        valor_ca,
                    )
                    for k, v in campos.items():
                        if k == 'discriminacao':
                            nova = (v or '').strip()
                            if disc_incoerente and nova:
                                setattr(existente, k, v)
                                existente.forma_pagamento = None
                                existente.nsu = ''
                            elif nova and not (existente.discriminacao or '').strip():
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
                        setattr(existente, k, v)
                    existente.save()
                    stats['atualizados'] += 1
                else:
                    NotaFiscalServico.objects.create(empresa=empresa, **campos)
                    stats['criados'] += 1
            except IntegrityError:
                stats['erros'] += 1
        cur = fim + timedelta(days=1)

    return stats
