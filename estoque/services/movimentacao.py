"""Entradas, transferências, baixas e preço médio ponderado."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from estoque.models import (
    EntradaEstoqueNota,
    MovimentoEstoque,
    ProdutoEstoque,
    RequisicaoEstoque,
    RequisicaoEstoqueItem,
    SaldoEstoqueSetor,
)
from estoque.setores import SetorEstoque
from notafiscalentrada.models import NotaFiscalEntradaItem


class EstoqueErro(ValueError):
    pass


def calcular_preco_medio(
    quantidade_atual: Decimal,
    custo_medio_atual: Decimal,
    quantidade_entrada: Decimal,
    preco_unitario_entrada: Decimal,
) -> Decimal:
    q_ant = quantidade_atual or Decimal('0')
    c_ant = custo_medio_atual or Decimal('0')
    q_nov = quantidade_entrada or Decimal('0')
    p_nov = preco_unitario_entrada or Decimal('0')
    q_total = q_ant + q_nov
    if q_total <= 0:
        return p_nov
    return (q_ant * c_ant + q_nov * p_nov) / q_total


def _saldo_setor(produto: ProdutoEstoque, setor: str) -> SaldoEstoqueSetor:
    obj, _ = SaldoEstoqueSetor.objects.get_or_create(
        produto=produto,
        setor=setor,
        defaults={'quantidade': Decimal('0')},
    )
    return obj


def _quantidade_farmacia(produto: ProdutoEstoque) -> Decimal:
    return produto.quantidade_estoque or Decimal('0')


def _ajustar_farmacia(produto: ProdutoEstoque, delta: Decimal) -> None:
    nova = _quantidade_farmacia(produto) + delta
    if nova < 0:
        raise EstoqueErro('Saldo insuficiente na farmácia.')
    produto.quantidade_estoque = nova
    produto.save(update_fields=['quantidade_estoque', 'atualizado_em'])


def _ajustar_setor(produto: ProdutoEstoque, setor: str, delta: Decimal) -> None:
    if setor == SetorEstoque.FARMACIA:
        _ajustar_farmacia(produto, delta)
        return
    saldo = _saldo_setor(produto, setor)
    nova = (saldo.quantidade or Decimal('0')) + delta
    if nova < 0:
        raise EstoqueErro(f'Saldo insuficiente no setor {setor}.')
    saldo.quantidade = nova
    saldo.save(update_fields=['quantidade', 'atualizado_em'])


@transaction.atomic
def gerar_entrada_desde_item_nota(
    item: NotaFiscalEntradaItem,
    *,
    usuario,
    marca: str = '',
    unidade_master: str = '',
    data_validade=None,
) -> EntradaEstoqueNota:
    if item.nota_fiscal.tipo_nota != 'comercio':
        raise EstoqueErro('Somente itens de NF de comércio geram estoque.')
    if EntradaEstoqueNota.objects.filter(nota_item=item).exists():
        raise EstoqueErro('Este item já gerou entrada de estoque.')

    empresa = item.nota_fiscal.empresa
    codigo = (item.codigo_produto or '').strip()
    if not codigo:
        raise EstoqueErro('Item sem código de produto.')

    produto, created = ProdutoEstoque.objects.get_or_create(
        empresa=empresa,
        codigo_produto=codigo,
        defaults={
            'descricao': (item.nome_produto or codigo)[:300],
            'marca': (marca or '')[:120],
            'unidade': (item.unidade or '')[:20],
            'unidade_master': (unidade_master or '')[:20],
        },
    )
    if not created:
        if marca:
            produto.marca = marca[:120]
        if unidade_master:
            produto.unidade_master = unidade_master[:20]
        if item.unidade:
            produto.unidade = item.unidade[:20]
        if item.nome_produto and len(item.nome_produto) > len(produto.descricao or ''):
            produto.descricao = item.nome_produto[:300]

    q_ent = item.quantidade or Decimal('0')
    p_ent = item.valor_unitario or Decimal('0')
    if q_ent <= 0:
        raise EstoqueErro('Quantidade do item inválida.')

    custo_novo = calcular_preco_medio(
        _quantidade_farmacia(produto),
        produto.valor_custo_medio,
        q_ent,
        p_ent,
    )
    produto.valor_custo_medio = custo_novo
    produto.valor_ultima_compra = p_ent
    produto.quantidade_estoque = _quantidade_farmacia(produto) + q_ent
    produto.save()

    mov = MovimentoEstoque.objects.create(
        empresa=empresa,
        produto=produto,
        tipo=MovimentoEstoque.Tipo.ENTRADA_NF,
        setor_origem='',
        setor_destino=SetorEstoque.FARMACIA,
        quantidade=q_ent,
        valor_unitario=p_ent,
        valor_custo_medio_apos=custo_novo,
        nota_item=item,
        usuario=usuario,
        observacao=f'NF {item.nota_fiscal.numero_nota}',
    )

    return EntradaEstoqueNota.objects.create(
        nota_item=item,
        produto=produto,
        quantidade=q_ent,
        valor_unitario=p_ent,
        marca=(marca or produto.marca or '')[:120],
        unidade_master=(unidade_master or produto.unidade_master or '')[:20],
        data_validade=data_validade,
        movimento=mov,
        criado_por=usuario,
    )


@transaction.atomic
def concluir_requisicao(requisicao: RequisicaoEstoque, *, usuario) -> None:
    if requisicao.status != RequisicaoEstoque.Status.RASCUNHO:
        raise EstoqueErro('Requisição já processada ou cancelada.')

    itens = list(requisicao.itens.select_related('produto'))
    if not itens:
        raise EstoqueErro('Requisição sem itens.')

    for linha in itens:
        q = linha.quantidade or Decimal('0')
        if q <= 0:
            continue
        produto = linha.produto
        p_med = produto.valor_custo_medio or Decimal('0')

        if requisicao.tipo == RequisicaoEstoque.Tipo.TRANSFERENCIA:
            _ajustar_farmacia(produto, -q)
            _ajustar_setor(produto, requisicao.setor_destino, q)
            MovimentoEstoque.objects.create(
                empresa=requisicao.empresa,
                produto=produto,
                tipo=MovimentoEstoque.Tipo.TRANSFERENCIA,
                setor_origem=SetorEstoque.FARMACIA,
                setor_destino=requisicao.setor_destino,
                quantidade=q,
                valor_unitario=p_med,
                valor_custo_medio_apos=p_med,
                requisicao=requisicao,
                usuario=usuario,
                observacao=requisicao.observacao or '',
            )
        elif requisicao.tipo == RequisicaoEstoque.Tipo.BAIXA_FARMACIA:
            _ajustar_farmacia(produto, -q)
            MovimentoEstoque.objects.create(
                empresa=requisicao.empresa,
                produto=produto,
                tipo=MovimentoEstoque.Tipo.BAIXA,
                setor_origem=SetorEstoque.FARMACIA,
                setor_destino=requisicao.setor_destino or requisicao.setor_consumo or '',
                quantidade=q,
                valor_unitario=p_med,
                valor_custo_medio_apos=p_med,
                requisicao=requisicao,
                usuario=usuario,
                observacao=requisicao.observacao or '',
            )
        elif requisicao.tipo == RequisicaoEstoque.Tipo.BAIXA_SETOR:
            origem = requisicao.setor_origem
            if origem == SetorEstoque.FARMACIA:
                raise EstoqueErro('Baixa de setor exige origem diferente da farmácia.')
            _ajustar_setor(produto, origem, -q)
            MovimentoEstoque.objects.create(
                empresa=requisicao.empresa,
                produto=produto,
                tipo=MovimentoEstoque.Tipo.BAIXA,
                setor_origem=origem,
                setor_destino=requisicao.setor_consumo or origem,
                quantidade=q,
                valor_unitario=p_med,
                valor_custo_medio_apos=p_med,
                requisicao=requisicao,
                usuario=usuario,
                observacao=requisicao.observacao or '',
            )
        linha.quantidade_atendida = q
        linha.save(update_fields=['quantidade_atendida'])

    requisicao.status = RequisicaoEstoque.Status.CONCLUIDA
    requisicao.concluida_em = timezone.now()
    requisicao.concluida_por = usuario
    requisicao.save(update_fields=['status', 'concluida_em', 'concluida_por'])
