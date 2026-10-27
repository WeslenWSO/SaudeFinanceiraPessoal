"""Importação de pedidos de venda Conta Azul → VendaContaAzul."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.db import IntegrityError
from django.utils.dateparse import parse_date, parse_datetime

from cobranca.models import Cobranca
from dashboard.conta_azul.caixa_acerto_venda import caixa_acerto_de_venda_ca
from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.venda_nfse import (
    buscar_venda_ca,
    cobranca_de_venda_ca,
    montar_discriminacao_venda_ca,
)
from dashboard.models import VendaContaAzul


def _parse_data_venda(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == '-':
        return parse_date(s[:10])
    dt = parse_datetime(s)
    return dt.date() if dt else None


def _upsert_venda_de_envelope(
    empresa,
    envelope: dict,
    *,
    cache_cobranca: dict[str, Cobranca] | None,
    dry_run: bool,
) -> tuple[bool, bool]:
    """Retorna (criado, ok)."""
    v = envelope.get('venda') if isinstance(envelope.get('venda'), dict) else envelope
    ca_id = str(v.get('id') or envelope.get('id') or '').strip()
    if not ca_id:
        return False, False

    numero = v.get('numero')
    data_v = _parse_data_venda(v.get('data_compromisso') or v.get('data'))
    cob = cobranca_de_venda_ca(envelope, cache_cobranca)
    caixa = caixa_acerto_de_venda_ca(empresa.pk, envelope)
    disc = montar_discriminacao_venda_ca(envelope)
    vend = envelope.get('vendedor') if isinstance(envelope.get('vendedor'), dict) else {}
    cp = v.get('condicao_pagamento') if isinstance(v.get('condicao_pagamento'), dict) else {}
    nsu = str(cp.get('nsu') or '').strip()[:100]

    if dry_run:
        return True, True

    defaults = {
        'numero_venda': int(numero) if numero is not None and str(numero).isdigit() else None,
        'data_venda': data_v,
        'forma_pagamento': cob,
        'caixa_acerto': caixa,
        'discriminacao_resumo': (disc or '')[:4000],
        'vendedor_nome': str(vend.get('nome') or '')[:120],
        'conta_financeira_ca_id': str(cp.get('id_conta_financeira') or '')[:36],
        'nsu': nsu,
    }
    try:
        _, created = VendaContaAzul.objects.update_or_create(
            empresa=empresa,
            conta_azul_id=ca_id,
            defaults=defaults,
        )
        return created, True
    except IntegrityError:
        return False, False


def importar_vendas_conta_azul(
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
        'detalhes_erro': 0,
    }
    cache_cobranca: dict[str, Cobranca] = {}
    cache_envelope: dict[str, dict] = {}

    try:
        resumos = client.buscar_vendas(data_de=data_de, data_ate=data_ate)
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}

    for resumo in resumos:
        if not isinstance(resumo, dict):
            stats['erros'] += 1
            continue
        vid = str(resumo.get('id') or '').strip()
        if not vid:
            stats['erros'] += 1
            continue
        envelope = buscar_venda_ca(client, vid, cache_envelope)
        if not envelope:
            stats['detalhes_erro'] += 1
            continue
        created, ok = _upsert_venda_de_envelope(
            empresa,
            envelope,
            cache_cobranca=cache_cobranca,
            dry_run=dry_run,
        )
        if not ok:
            stats['erros'] += 1
        elif created:
            stats['criados'] += 1
        else:
            stats['atualizados'] += 1

    return stats


def aplicar_venda_cache_em_nota(nota, venda: VendaContaAzul) -> list[str]:
    """Atualiza NF local com dados já sincronizados da venda. Retorna update_fields."""
    campos: list[str] = []
    if venda.forma_pagamento_id and not nota.forma_pagamento_id:
        nota.forma_pagamento = venda.forma_pagamento
        campos.append('forma_pagamento')
    if venda.caixa_acerto and not (getattr(nota, 'caixa_acerto_sugerido', None) or '').strip():
        nota.caixa_acerto_sugerido = venda.caixa_acerto
        campos.append('caixa_acerto_sugerido')
    if venda.nsu and not (nota.nsu or '').strip():
        nota.nsu = venda.nsu
        campos.append('nsu')
    resumo = (venda.discriminacao_resumo or '').strip()
    if resumo and 'PAGAMENTO' in resumo.upper():
        disc = (nota.discriminacao or '').strip()
        if not disc or 'PAGAMENTO' not in disc.upper():
            nota.discriminacao = resumo
            campos.append('discriminacao')
    return campos
