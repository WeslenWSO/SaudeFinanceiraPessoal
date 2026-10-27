"""Enriquece NFS-e importada do Conta Azul com dados da venda (discriminação e pagamento)."""

from __future__ import annotations

from typing import Any

from cobranca.models import Cobranca
from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.forma_pagamento_ca import _cobranca_de_item, _texto_forma_pagamento_item


def _corpo_venda(envelope: dict | None) -> dict:
    if not isinstance(envelope, dict):
        return {}
    venda = envelope.get('venda')
    if isinstance(venda, dict):
        return venda
    return envelope


def _texto_de_valor(raw: Any) -> str:
    if raw is None:
        return ''
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, (int, float)):
        return str(raw)
    if isinstance(raw, dict):
        for key in ('descricao', 'nome', 'texto', 'observacao', 'valor'):
            t = _texto_de_valor(raw.get(key))
            if t:
                return t
    if isinstance(raw, list):
        partes = [_texto_de_valor(x) for x in raw]
        partes = [p for p in partes if p]
        return '\n'.join(partes)
    return str(raw).strip()


def _item_pagamento_de_venda(envelope: dict | None) -> dict:
    """Monta dict compatível com _texto_forma_pagamento_item do sync financeiro."""
    if not isinstance(envelope, dict):
        return {}
    for bloco in (
        envelope.get('evento_financeiro'),
        _corpo_venda(envelope),
        envelope,
    ):
        if not isinstance(bloco, dict):
            continue
        item = dict(bloco)
        if _texto_forma_pagamento_item(item):
            return item
        for key in ('condicao_pagamento', 'condicao_pagamento_venda', 'pagamento'):
            val = bloco.get(key)
            if val is not None and val != '':
                item['forma_pagamento'] = val
                if _texto_forma_pagamento_item(item):
                    return item
        parcelas = bloco.get('parcelas') or bloco.get('condicoes_pagamento')
        if isinstance(parcelas, list) and parcelas:
            p0 = parcelas[0] if isinstance(parcelas[0], dict) else {}
            merged = {**item, **p0}
            if _texto_forma_pagamento_item(merged):
                return merged
    return {}


def cobranca_de_venda_ca(
    envelope: dict | None,
    *,
    cache_cobranca: dict[str, Cobranca] | None = None,
) -> Cobranca | None:
    item = _item_pagamento_de_venda(envelope)
    if not item:
        return None
    return _cobranca_de_item(item, cache_cobranca)


def _discriminacao_de_itens_venda(itens_raw: Any) -> str:
    if not itens_raw:
        return ''
    if isinstance(itens_raw, dict):
        itens_raw = (
            itens_raw.get('itens')
            or itens_raw.get('items')
            or itens_raw.get('data')
            or []
        )
    if not isinstance(itens_raw, list):
        return ''
    linhas: list[str] = []
    for it in itens_raw:
        if not isinstance(it, dict):
            continue
        serv = it.get('servico') if isinstance(it.get('servico'), dict) else {}
        desc = _texto_de_valor(
            it.get('descricao')
            or it.get('nome')
            or serv.get('descricao')
            or serv.get('nome')
        )
        if not desc:
            continue
        qtd = it.get('quantidade') or it.get('qtd') or 1
        val = it.get('valor') or it.get('valor_total') or it.get('preco')
        if val is not None and str(val).strip():
            linhas.append(f'{desc} — {qtd} x {val}')
        else:
            linhas.append(desc)
    return '\n'.join(linhas).strip()


def montar_discriminacao_venda_ca(envelope: dict | None, itens_payload: Any = None) -> str:
    if not isinstance(envelope, dict):
        return ''
    v = _corpo_venda(envelope)
    candidatos: list[str] = []
    for fonte in (v, envelope):
        for key in (
            'observacao',
            'observacoes',
            'informacao_complementar',
            'informacoes_complementares',
            'informacoes_adicionais',
            'texto_nota',
            'discriminacao',
            'descricao',
        ):
            t = _texto_de_valor(fonte.get(key))
            if t:
                candidatos.append(t)
    disc_itens = _discriminacao_de_itens_venda(itens_payload)
    if disc_itens:
        candidatos.append(disc_itens)

    for t in candidatos:
        up = t.upper()
        if any(m in up for m in ('PAGAMENTO', 'PACIENTE', 'EXAME', 'PROCEDIMENTO', 'CPF:')):
            return t
    for t in candidatos:
        if len(t) >= 30:
            return t
    return candidatos[0] if candidatos else ''


def _garantir_pagamento_na_discriminacao(disc: str, forma_txt: str) -> str:
    disc = (disc or '').strip()
    forma_txt = (forma_txt or '').strip()
    if not forma_txt:
        return disc
    if 'PAGAMENTO' in disc.upper():
        return disc
    if disc:
        return f'{disc}\nPAGAMENTO: {forma_txt}'
    return f'PAGAMENTO: {forma_txt}'


def buscar_venda_ca(
    client: ContaAzulClient,
    id_venda: str,
    cache: dict[str, dict],
) -> dict:
    vid = (id_venda or '').strip()
    if not vid:
        return {}
    if vid in cache:
        return cache[vid]
    try:
        data = client.buscar_venda_por_id(vid)
    except ContaAzulAPIError:
        data = {}
    cache[vid] = data if isinstance(data, dict) else {}
    return cache[vid]


def enriquecer_campos_nfse_com_venda_ca(
    client: ContaAzulClient,
    item_nfse: dict,
    campos: dict[str, Any],
    *,
    cache_vendas: dict[str, dict],
    cache_cobranca: dict[str, Cobranca] | None = None,
) -> dict[str, Any]:
    """
    Completa discriminação e forma de pagamento a partir da venda CA (id_venda na NFS-e).
    """
    id_venda = str(item_nfse.get('id_venda') or '').strip()
    if not id_venda:
        return campos

    envelope = buscar_venda_ca(client, id_venda, cache_vendas)
    if not envelope:
        return campos

    itens_payload: Any = None
    try:
        itens_payload = client.buscar_itens_venda(id_venda)
    except ContaAzulAPIError:
        itens_payload = None

    disc = montar_discriminacao_venda_ca(envelope, itens_payload)
    item_pg = _item_pagamento_de_venda(envelope)
    forma_txt = _texto_forma_pagamento_item(item_pg)
    if disc:
        campos['discriminacao'] = _garantir_pagamento_na_discriminacao(disc, forma_txt)
    elif forma_txt:
        base = (campos.get('discriminacao') or '').strip()
        campos['discriminacao'] = _garantir_pagamento_na_discriminacao(base, forma_txt)

    cob = cobranca_de_venda_ca(envelope, cache_cobranca=cache_cobranca)
    if cob is not None:
        campos['forma_pagamento'] = cob

    return campos
