"""Exportação de produtos de estoque para Excel (.xlsx)."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from estoque.import_planilha import COLUNAS_MODELO
from estoque.models import ProdutoEstoque


def _num(val) -> float | int | str:
    if val is None:
        return ''
    if isinstance(val, Decimal):
        return float(val)
    return val


def exportar_produtos_cadastro_xlsx(produtos) -> bytes:
    """Colunas compatíveis com o modelo de importação."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Estoque'
    extras = ('Unidade', 'Un. master', 'Un./master', 'Fornecedor', 'Natureza')
    ws.append([*COLUNAS_MODELO, *extras])
    for p in produtos:
        ws.append(
            [
                p.codigo_produto,
                p.descricao,
                p.marca or '',
                _num(p.quantidade_estoque),
                _num(p.quantidade_estoque_contabil),
                _num(p.estoque_minimo),
                p.dias_entrega_fornecedor if p.dias_entrega_fornecedor is not None else '',
                _num(p.valor_ultima_compra),
                _num(p.valor_custo_medio),
                _num(p.valor_custo_contabil),
                p.unidade or '',
                p.unidade_master or '',
                _num(p.quantidade_por_master) if p.quantidade_por_master else '',
                p.fornecedor_rotulo or '',
                p.get_natureza_display() if hasattr(p, 'get_natureza_display') else '',
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_farmacia_xlsx(produtos) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Farmácia'
    ws.append(
        [
            'Código',
            'Descrição',
            'Marca',
            'Fornecedor',
            'Un. master',
            'Un./master',
            'Unidade',
            'Qt. farmácia',
            'Estoque mín.',
            'Dias entrega',
            'Preço médio',
            'Abaixo do mínimo',
        ]
    )
    for p in produtos:
        ws.append(
            [
                p.codigo_produto,
                p.descricao,
                p.marca or '',
                p.fornecedor_rotulo or '',
                p.unidade_master or '',
                _num(p.quantidade_por_master) if p.quantidade_por_master else '',
                p.unidade or '',
                _num(p.quantidade_estoque),
                _num(p.estoque_minimo),
                p.dias_entrega_fornecedor if p.dias_entrega_fornecedor is not None else '',
                _num(p.valor_custo_medio),
                'Sim' if p.abaixo_estoque_minimo else 'Não',
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def queryset_produtos_cadastro_export(empresa_id: int | None, *, busca: str = ''):
    from django.db.models import Q

    from estoque.models import ProdutoEstoque

    if not empresa_id:
        return ProdutoEstoque.objects.none()
    qs = ProdutoEstoque.objects.filter(empresa_id=empresa_id).select_related('fornecedor')
    busca = (busca or '').strip()
    if busca:
        qs = qs.filter(
            Q(codigo_produto__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(marca__icontains=busca),
        )
    return qs.order_by('codigo_produto', 'descricao')


def queryset_farmacia_export(
    empresa_id: int | None,
    *,
    busca: str = '',
    somente_alertas: bool = False,
):
    from django.db.models import Q

    from estoque.alertas import queryset_abaixo_estoque_minimo
    from estoque.models import NaturezaEstoque, ProdutoEstoque

    if not empresa_id:
        return ProdutoEstoque.objects.none()
    if somente_alertas:
        qs = queryset_abaixo_estoque_minimo(empresa_id)
    else:
        qs = ProdutoEstoque.objects.filter(
            empresa_id=empresa_id,
            natureza=NaturezaEstoque.CONSUMIVEL,
        ).select_related('fornecedor')
    busca = (busca or '').strip()
    if busca:
        qs = qs.filter(
            Q(codigo_produto__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(marca__icontains=busca),
        )
    return qs.order_by('descricao')
