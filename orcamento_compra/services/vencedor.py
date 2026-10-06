"""Cálculo e gravação dos orçamentos vencedores por fornecedor."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from orcamento_compra.models import (
    OrcamentoCompra,
    OrcamentoCompraPreco,
    OrcamentoCompraResultadoVencedor,
    OrcamentoCompraResultadoVencedorItem,
)


def _precos_por_orcamento(orcamento: OrcamentoCompra) -> dict[tuple[int, int], OrcamentoCompraPreco]:
    return {
        (p.item_id, p.coluna_fornecedor_id): p
        for p in OrcamentoCompraPreco.objects.filter(item__orcamento=orcamento).select_related(
            'item', 'coluna_fornecedor'
        )
    }


def vencedor_por_item(orcamento: OrcamentoCompra) -> list[dict]:
    """
    Para cada item, retorna a coluna com menor total cotado.
    Empate: vence a coluna de menor ordem.
    """
    colunas = list(orcamento.fornecedores.order_by('ordem', 'id'))
    itens = list(orcamento.itens.order_by('ordem', 'id'))
    precos = _precos_por_orcamento(orcamento)
    saida: list[dict] = []

    for item in itens:
        melhor_col = None
        melhor_total: Decimal | None = None
        melhor_unit: Decimal | None = None
        melhor_preco: OrcamentoCompraPreco | None = None

        for col in colunas:
            preco = precos.get((item.pk, col.pk))
            if not preco:
                continue
            total = preco.total_calculado()
            if total is None:
                continue
            if melhor_total is None or total < melhor_total:
                melhor_total = total
                melhor_col = col
                melhor_unit = preco.preco_unitario
                melhor_preco = preco

        if melhor_col is None or melhor_total is None:
            continue

        saida.append({
            'item': item,
            'coluna': melhor_col,
            'preco': melhor_preco,
            'preco_unitario': melhor_unit,
            'preco_total': melhor_total,
        })
    return saida


def agrupar_vencedores_por_fornecedor(orcamento: OrcamentoCompra) -> dict[int, list[dict]]:
    grupos: dict[int, list[dict]] = defaultdict(list)
    for row in vencedor_por_item(orcamento):
        grupos[row['coluna'].pk].append(row)
    return grupos


@transaction.atomic
def gerar_orcamentos_vencedores(orcamento: OrcamentoCompra) -> list[OrcamentoCompraResultadoVencedor]:
    """Apaga resultados anteriores e grava um pedido vencedor por fornecedor."""
    OrcamentoCompraResultadoVencedor.objects.filter(orcamento=orcamento).delete()
    grupos = agrupar_vencedores_por_fornecedor(orcamento)
    criados: list[OrcamentoCompraResultadoVencedor] = []

    for coluna in orcamento.fornecedores.order_by('ordem', 'id'):
        linhas = grupos.get(coluna.pk) or []
        if not linhas:
            continue
        total = sum((r['preco_total'] for r in linhas), Decimal('0'))
        resultado = OrcamentoCompraResultadoVencedor.objects.create(
            orcamento=orcamento,
            coluna_fornecedor=coluna,
            total_geral=total,
        )
        for ordem, row in enumerate(linhas, start=1):
            item = row['item']
            OrcamentoCompraResultadoVencedorItem.objects.create(
                resultado=resultado,
                item=item,
                descricao=item.descricao,
                unidade=item.unidade,
                quantidade=item.quantidade,
                preco_unitario=row['preco_unitario'],
                preco_total=row['preco_total'],
                ordem=ordem,
            )
        criados.append(resultado)

    orcamento.status = OrcamentoCompra.STATUS_CONCLUIDO
    orcamento.atualizado_em = timezone.now()
    orcamento.save(update_fields=['status', 'atualizado_em'])
    return criados
