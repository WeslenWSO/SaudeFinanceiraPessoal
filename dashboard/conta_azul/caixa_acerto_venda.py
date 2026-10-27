"""Caixa do acerto de caixa SF a partir da venda Conta Azul."""

from __future__ import annotations

import unicodedata

from extrato.models import ContaBancaria
from faturamento_medico.models import CAIXAS_ACERTO_CHOICES
from faturamento_medico.services.contas_caixa_acerto import (
    conta_elegivel_acerto_caixa,
    queryset_contas_caixa_cadastro,
)


def _normalizar_nome(s: str) -> str:
    s = (s or '').strip().casefold()
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def _corpo_venda(envelope: dict | None) -> dict:
    if not isinstance(envelope, dict):
        return {}
    venda = envelope.get('venda')
    if isinstance(venda, dict):
        return venda
    return envelope


def caixa_acerto_por_nome_vendedor(empresa_id: int, nome_vendedor: str) -> str:
    nome = (nome_vendedor or '').strip()
    if not nome or not empresa_id:
        return ''
    norm = _normalizar_nome(nome)
    primeiro = norm.split()[0] if norm else ''

    for conta in queryset_contas_caixa_cadastro(empresa_id):
        desc_norm = _normalizar_nome(conta.descricao or '')
        if norm in desc_norm or (primeiro and primeiro in desc_norm.split()):
            return str(conta.pk)

    for legado, rotulo in CAIXAS_ACERTO_CHOICES:
        if _normalizar_nome(legado) == norm or _normalizar_nome(legado) == primeiro:
            conta = (
                queryset_contas_caixa_cadastro(empresa_id)
                .filter(descricao__icontains=legado)
                .first()
            )
            if conta:
                return str(conta.pk)
            return legado
        if primeiro and _normalizar_nome(rotulo).startswith(primeiro):
            conta = (
                queryset_contas_caixa_cadastro(empresa_id)
                .filter(descricao__icontains=legado)
                .first()
            )
            if conta:
                return str(conta.pk)
    return ''


def caixa_acerto_de_venda_ca(empresa_id: int, envelope: dict | None) -> str:
    if not envelope or not empresa_id:
        return ''
    v = _corpo_venda(envelope)
    cp = v.get('condicao_pagamento') if isinstance(v.get('condicao_pagamento'), dict) else {}
    ca_id = str(cp.get('id_conta_financeira') or '').strip()
    if ca_id:
        conta = ContaBancaria.objects.filter(
            empresa_id=empresa_id,
            conta_azul_id=ca_id,
        ).first()
        if conta and conta_elegivel_acerto_caixa(conta):
            return str(conta.pk)

    vend = envelope.get('vendedor') if isinstance(envelope.get('vendedor'), dict) else {}
    return caixa_acerto_por_nome_vendedor(empresa_id, str(vend.get('nome') or ''))
