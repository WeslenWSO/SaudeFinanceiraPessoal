"""Alertas de estoque abaixo do mínimo."""

from __future__ import annotations

from django.db.models import F, QuerySet

from estoque.models import NaturezaEstoque, ProdutoEstoque


def queryset_abaixo_estoque_minimo(empresa_id: int | None) -> QuerySet[ProdutoEstoque]:
    if not empresa_id:
        return ProdutoEstoque.objects.none()
    return (
        ProdutoEstoque.objects.filter(
            empresa_id=empresa_id,
            natureza=NaturezaEstoque.CONSUMIVEL,
            estoque_minimo__gt=0,
        )
        .filter(quantidade_estoque__lt=F('estoque_minimo'))
        .order_by('descricao', 'codigo_produto')
    )


def contar_abaixo_estoque_minimo(empresa_id: int | None) -> int:
    return queryset_abaixo_estoque_minimo(empresa_id).count()
