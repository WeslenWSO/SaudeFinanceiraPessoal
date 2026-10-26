"""Coerência entre discriminação da NFS-e e valor da nota."""

from __future__ import annotations

import re
from decimal import Decimal

from notasfiscais.utils import _PADRAO_VALOR_MONETARIO, _normalizar_valor_monetario_str

_EPS = Decimal('0.05')


def _valores_procedimentos_no_cabecalho(discriminacao: str) -> list[Decimal]:
    if not discriminacao:
        return []
    head = discriminacao
    upper = head.upper()
    for sep in ('PACIENTE:', 'CPF:', 'PAGAMENTO:', 'EXAME REALIZADO'):
        idx = upper.find(sep)
        if idx > 0:
            head = head[:idx]
    valores: list[Decimal] = []
    for match in _PADRAO_VALOR_MONETARIO.finditer(head):
        val = _normalizar_valor_monetario_str(match.group(1))
        if val is not None and val > 0:
            valores.append(val)
    return valores


def discriminacao_valor_coerente(
    discriminacao: str | None,
    valor_nf: Decimal | None,
) -> bool:
    """
    False quando a discriminação traz valores de procedimento que não batem com o total da NF
    (ex.: XML de outra nota reaproveitado no mesmo número).
    """
    if not (discriminacao or '').strip() or valor_nf is None:
        return True
    valor_nf = Decimal(str(valor_nf))
    if valor_nf <= 0:
        return True
    valores = _valores_procedimentos_no_cabecalho(discriminacao)
    if not valores:
        return True
    total = sum(valores)
    if len(valores) == 1:
        return abs(valores[0] - valor_nf) <= _EPS
    return abs(total - valor_nf) <= _EPS


def extrair_id_venda_conta_azul(observacoes: str | None) -> str:
    if not observacoes:
        return ''
    m = re.search(r'id_venda:\s*(\S+)', observacoes, re.IGNORECASE)
    return (m.group(1).strip() if m else '')
