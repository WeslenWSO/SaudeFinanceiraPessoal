"""Análise de compra — última entrada NF × saldo atual."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import Q

from estoque.models import EntradaEstoqueNota, NaturezaEstoque, ProdutoEstoque


def _data_ultima_compra(entrada: EntradaEstoqueNota | None) -> date | None:
    if entrada is None:
        return None
    item = entrada.nota_item
    if item and item.nota_fiscal_id and item.nota_fiscal.data_emissao:
        dt = item.nota_fiscal.data_emissao
        return dt.date() if isinstance(dt, datetime) else dt
    if entrada.criado_em:
        return entrada.criado_em.date()
    return None


def _fornecedor_exibicao(produto: ProdutoEstoque, entrada: EntradaEstoqueNota | None) -> str:
    if entrada and entrada.nota_item_id:
        nf = entrada.nota_item.nota_fiscal
        if nf.fornecedor_id and nf.fornecedor:
            return (nf.fornecedor.nome_fantasia or nf.fornecedor.razao or '').strip()
        nome = (nf.fornecedor_nome or '').strip()
        if nome:
            return nome
    return produto.fornecedor_rotulo or ''


def _mapa_ultima_entrada_por_produto(empresa_id: int) -> dict[int, EntradaEstoqueNota]:
    out: dict[int, EntradaEstoqueNota] = {}
    qs = (
        EntradaEstoqueNota.objects.filter(produto__empresa_id=empresa_id)
        .select_related(
            'nota_item__nota_fiscal__fornecedor',
            'produto__fornecedor',
        )
        .order_by('-criado_em')
    )
    for entrada in qs.iterator(chunk_size=500):
        pid = entrada.produto_id
        if pid not in out:
            out[pid] = entrada
    return out


def queryset_analise_compra(
    empresa_id: int | None,
    *,
    busca: str = '',
    natureza: str | None = NaturezaEstoque.CONSUMIVEL,
):
    if not empresa_id:
        return ProdutoEstoque.objects.none()
    qs = ProdutoEstoque.objects.filter(empresa_id=empresa_id).select_related('fornecedor')
    if natureza:
        qs = qs.filter(natureza=natureza)
    busca = (busca or '').strip()
    if busca:
        qs = qs.filter(
            Q(codigo_produto__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(marca__icontains=busca),
        )
    return qs.order_by('codigo_produto', 'descricao')


def montar_linhas_analise_compra(
    empresa_id: int | None,
    *,
    busca: str = '',
    natureza: str | None = NaturezaEstoque.CONSUMIVEL,
) -> list[dict[str, Any]]:
    if not empresa_id:
        return []
    ultimas = _mapa_ultima_entrada_por_produto(empresa_id)
    linhas: list[dict[str, Any]] = []
    for produto in queryset_analise_compra(empresa_id, busca=busca, natureza=natureza):
        entrada = ultimas.get(produto.pk)
        data_uc = _data_ultima_compra(entrada)
        qtd_uc = entrada.quantidade if entrada else None
        linhas.append(
            {
                'codigo_produto': produto.codigo_produto,
                'descricao': produto.descricao,
                'marca': (produto.marca or '').strip() or (entrada.marca if entrada else '') or '',
                'fornecedor': _fornecedor_exibicao(produto, entrada),
                'qtd_ultima_compra': qtd_uc,
                'qtd_ultima_compra_fmt': _fmt_qtd(qtd_uc),
                'data_ultima_compra': data_uc,
                'data_ultima_compra_fmt': data_uc.strftime('%d/%m/%Y') if data_uc else '—',
                'estoque': produto.quantidade_estoque,
                'estoque_fmt': _fmt_qtd(produto.quantidade_estoque),
                'unidade': produto.unidade or '',
                'unidade_master': produto.unidade_master or '',
                'qtd_master': produto.quantidade_por_master,
                'qtd_master_fmt': _fmt_qtd(produto.quantidade_por_master) if produto.quantidade_por_master else '—',
                'dias_entrega': produto.dias_entrega_fornecedor,
                'dias_entrega_fmt': (
                    str(produto.dias_entrega_fornecedor)
                    if produto.dias_entrega_fornecedor is not None
                    else '—'
                ),
            }
        )
    return linhas


def _fmt_qtd(val: Decimal | None) -> str:
    if val is None:
        return '—'
    d = Decimal(str(val))
    s = format(d, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s.replace('.', ',')
