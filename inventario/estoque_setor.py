"""Saldo operacional por setor (farmácia central vs setores clínicos)."""

from __future__ import annotations

from decimal import Decimal

from estoque.models import ProdutoEstoque, SaldoEstoqueSetor
from estoque.setores import SetorEstoque


def quantidade_sistema_no_setor(produto: ProdutoEstoque, setor: str) -> Decimal:
    cod = (setor or SetorEstoque.FARMACIA).strip()
    if cod == SetorEstoque.FARMACIA:
        return produto.quantidade_estoque or Decimal('0')
    saldo = SaldoEstoqueSetor.objects.filter(produto=produto, setor=cod).first()
    if not saldo:
        return Decimal('0')
    return saldo.quantidade or Decimal('0')
