"""Análise de compra — última entrada NF × saldo atual."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from decimal import InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import (
    AnaliseCompraSalva,
    AnaliseCompraSalvaItem,
    EntradaEstoqueNota,
    NaturezaEstoque,
    ProdutoEstoque,
)


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
                'produto_id': produto.pk,
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


def parse_quantidade_br(raw) -> Decimal | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


@transaction.atomic
def criar_analise_compra_salva(
    empresa_id: int,
    *,
    titulo: str,
    observacao: str,
    produto_ids: list[int],
    usuario,
) -> AnaliseCompraSalva:
    ids = sorted({int(x) for x in produto_ids if x})
    if not ids:
        raise ValueError('Selecione ao menos um produto.')
    titulo = (titulo or '').strip() or timezone.localdate().strftime('Análise %d/%m/%Y')
    ultimas = _mapa_ultima_entrada_por_produto(empresa_id)
    produtos = {
        p.pk: p
        for p in ProdutoEstoque.objects.filter(empresa_id=empresa_id, pk__in=ids)
    }
    if len(produtos) != len(ids):
        raise ValueError('Um ou mais produtos não pertencem à empresa selecionada.')
    analise = AnaliseCompraSalva.objects.create(
        empresa_id=empresa_id,
        titulo=titulo[:200],
        observacao=(observacao or '').strip(),
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
    )
    ordem = 0
    for pid in ids:
        produto = produtos[pid]
        entrada = ultimas.get(produto.pk)
        ordem += 1
        AnaliseCompraSalvaItem.objects.create(
            analise=analise,
            produto=produto,
            codigo_produto=produto.codigo_produto,
            descricao=produto.descricao,
            marca=(produto.marca or '').strip() or (entrada.marca if entrada else ''),
            fornecedor_texto=_fornecedor_exibicao(produto, entrada),
            qtd_ultima_compra=entrada.quantidade if entrada else None,
            data_ultima_compra=_data_ultima_compra(entrada),
            estoque_registrado=produto.quantidade_estoque or Decimal('0'),
            unidade=produto.unidade or '',
            unidade_master=produto.unidade_master or '',
            qtd_master=produto.quantidade_por_master or Decimal('0'),
            dias_entrega=produto.dias_entrega_fornecedor,
            quantidade_desejada=Decimal('0'),
            ordem=ordem,
        )
    return analise


def montar_linhas_analise_salva(analise: AnaliseCompraSalva) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for it in analise.itens.select_related('produto').order_by('ordem', 'id'):
        produto = it.produto
        estoque_atual = produto.quantidade_estoque if produto else it.estoque_registrado
        linhas.append(
            {
                'item_id': it.pk,
                'produto_id': it.produto_id,
                'codigo_produto': it.codigo_produto,
                'descricao': it.descricao,
                'marca': it.marca or '—',
                'fornecedor': it.fornecedor_texto or '—',
                'qtd_ultima_compra': it.qtd_ultima_compra,
                'qtd_ultima_compra_fmt': _fmt_qtd(it.qtd_ultima_compra),
                'data_ultima_compra': it.data_ultima_compra,
                'data_ultima_compra_fmt': (
                    it.data_ultima_compra.strftime('%d/%m/%Y') if it.data_ultima_compra else '—'
                ),
                'estoque': estoque_atual,
                'estoque_fmt': _fmt_qtd(estoque_atual),
                'estoque_registrado_fmt': _fmt_qtd(it.estoque_registrado),
                'unidade': it.unidade or '—',
                'unidade_master': it.unidade_master or '—',
                'qtd_master_fmt': _fmt_qtd(it.qtd_master) if it.qtd_master else '—',
                'dias_entrega_fmt': str(it.dias_entrega) if it.dias_entrega is not None else '—',
                'quantidade_desejada': it.quantidade_desejada,
                'quantidade_desejada_fmt': _fmt_qtd(it.quantidade_desejada),
            }
        )
    return linhas


@transaction.atomic
def salvar_quantidades_desejadas(analise: AnaliseCompraSalva, valores: dict[int, Decimal]) -> int:
    atualizados = 0
    for item in analise.itens.all():
        if item.pk not in valores:
            continue
        q = valores[item.pk]
        if q < 0:
            q = Decimal('0')
        if item.quantidade_desejada != q:
            item.quantidade_desejada = q
            item.save(update_fields=['quantidade_desejada'])
            atualizados += 1
    analise.save(update_fields=['atualizado_em'])
    return atualizados


@transaction.atomic
def gerar_orcamento_compra_da_analise(analise: AnaliseCompraSalva, *, usuario) -> 'OrcamentoCompra':
    from orcamento_compra.models import OrcamentoCompra, OrcamentoCompraItem

    if analise.orcamento_gerado_id:
        return analise.orcamento_gerado
    itens = list(
        analise.itens.filter(quantidade_desejada__gt=0).order_by('ordem', 'id'),
    )
    if not itens:
        raise ValueError('Informe a quantidade desejada em ao menos um produto.')
    orc = OrcamentoCompra.objects.create(
        empresa_id=analise.empresa_id,
        titulo=f'Compra — {analise.titulo}'[:200],
        observacao=(
            f'Gerado a partir da análise de compra #{analise.pk} em '
            f'{timezone.localdate().strftime("%d/%m/%Y")}.'
        ),
        status=OrcamentoCompra.STATUS_COTACAO,
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
    )
    ordem = 0
    for it in itens:
        ordem += 1
        unidade = (it.unidade or 'UN').strip() or 'UN'
        OrcamentoCompraItem.objects.create(
            orcamento=orc,
            produto=it.produto,
            codigo_produto_comercio=it.codigo_produto,
            descricao=it.descricao,
            unidade=unidade[:20],
            quantidade=it.quantidade_desejada,
            ordem=ordem,
        )
    analise.orcamento_gerado = orc
    analise.save(update_fields=['orcamento_gerado', 'atualizado_em'])
    return orc


def _fmt_qtd(val: Decimal | None) -> str:
    if val is None:
        return '—'
    d = Decimal(str(val))
    s = format(d, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s.replace('.', ',')
