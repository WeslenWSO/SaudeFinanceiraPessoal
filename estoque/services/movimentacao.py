"""Entradas, transferências, baixas e preço médio ponderado."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from estoque.models import (
    EntradaEstoqueNota,
    MovimentoEstoque,
    NaturezaEstoque,
    ProdutoEstoque,
    RequisicaoEstoque,
    RequisicaoEstoqueItem,
    SaldoEstoqueSetor,
)
from estoque.setores import SetorEstoque
from notafiscalentrada.models import NotaFiscalEntradaItem


class EstoqueErro(ValueError):
    pass


def converter_quantidade_nf_para_estoque(
    q_nf: Decimal,
    p_nf: Decimal,
    *,
    quantidade_por_master: Decimal | None,
    unidade_master: str = '',
    unidade_nf: str = '',
    unidade_consumo: str = '',
) -> tuple[Decimal, Decimal, str]:
    """
    Se informado fator (>0), trata q_nf como unidade master (ex.: 1 CX)
    e retorna quantidade/preço na unidade de estoque (ex.: 10 UN, preço/UN).
    """
    fator = quantidade_por_master or Decimal('0')
    if fator <= 0:
        return q_nf, p_nf, ''
    um = (unidade_master or unidade_nf or 'master').strip()
    uc = (unidade_consumo or 'UN').strip()
    q_est = q_nf * fator
    p_est = p_nf / fator if fator else p_nf
    det = f'{q_nf} {um} × {fator} → {q_est} {uc}'
    return q_est, p_est, det


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
    saldo.save(update_fields=['quantidade'])


@transaction.atomic
def gerar_entrada_desde_item_nota(
    item: NotaFiscalEntradaItem,
    *,
    usuario,
    marca: str = '',
    unidade_master: str = '',
    quantidade_por_master=None,
    data_validade=None,
    natureza: str = NaturezaEstoque.CONSUMIVEL,
    setor_localizacao: str = '',
    unidade_consumo: str = '',
) -> EntradaEstoqueNota:
    if item.nota_fiscal.tipo_nota != 'comercio':
        raise EstoqueErro('Somente itens de NF de comércio geram estoque.')
    if EntradaEstoqueNota.objects.filter(nota_item=item).exists():
        raise EstoqueErro('Este item já gerou entrada de estoque.')

    empresa = item.nota_fiscal.empresa
    codigo = (item.codigo_produto or '').strip()
    if not codigo:
        raise EstoqueErro('Item sem código de produto.')
    if natureza not in NaturezaEstoque.values:
        natureza = NaturezaEstoque.CONSUMIVEL
    setor_entrada = (
        SetorEstoque.IMOBILIZADO
        if natureza == NaturezaEstoque.IMOBILIZADO
        else SetorEstoque.FARMACIA
    )
    setor_loc = (setor_localizacao or '').strip()
    if natureza == NaturezaEstoque.IMOBILIZADO and not setor_loc:
        raise EstoqueErro('Informe o setor de localização do imobilizado.')

    produto, created = ProdutoEstoque.objects.get_or_create(
        empresa=empresa,
        codigo_produto=codigo,
        defaults={
            'natureza': natureza,
            'setor_localizacao': setor_loc[:32] if setor_loc else '',
            'descricao': (item.nome_produto or codigo)[:300],
            'marca': (marca or '')[:120],
            'unidade': (item.unidade or '')[:20],
            'unidade_master': (unidade_master or '')[:20],
            'quantidade_por_master': quantidade_por_master or Decimal('0'),
        },
    )
    q_master = quantidade_por_master if quantidade_por_master is not None else None
    if not created:
        if produto.natureza != natureza:
            rotulo = produto.get_natureza_display()
            raise EstoqueErro(
                f'Código {codigo} já está cadastrado como {rotulo}. '
                'Use a tela correta de estoque ou outro código.',
            )
        if marca:
            produto.marca = marca[:120]
        if unidade_master:
            produto.unidade_master = unidade_master[:20]
        if q_master is not None and q_master > 0:
            produto.quantidade_por_master = q_master
        if item.nome_produto and len(item.nome_produto) > len(produto.descricao or ''):
            produto.descricao = item.nome_produto[:300]
    if item.nota_fiscal.fornecedor_id:
        produto.fornecedor_id = item.nota_fiscal.fornecedor_id
    if setor_loc:
        produto.setor_localizacao = setor_loc[:32]

    q_nf = item.quantidade or Decimal('0')
    p_nf = item.valor_unitario or Decimal('0')
    if q_nf <= 0:
        raise EstoqueErro('Quantidade do item inválida.')

    fator_master = (
        quantidade_por_master
        if quantidade_por_master is not None and quantidade_por_master > 0
        else None
    )

    q_ent, p_ent, det_conv = converter_quantidade_nf_para_estoque(
        q_nf,
        p_nf,
        quantidade_por_master=fator_master,
        unidade_master=unidade_master or produto.unidade_master or '',
        unidade_nf=(item.unidade or '')[:20],
        unidade_consumo=unidade_consumo or produto.unidade or '',
    )
    if fator_master and fator_master > 0:
        um = (unidade_master or item.unidade or produto.unidade_master or '')[:20]
        if um:
            produto.unidade_master = um
        produto.quantidade_por_master = fator_master
        uc = (unidade_consumo or produto.unidade or 'UN').strip()[:20]
        if uc:
            produto.unidade = uc
    elif item.unidade:
        produto.unidade = item.unidade[:20]

    if q_ent <= 0:
        raise EstoqueErro('Quantidade convertida inválida (verifique o fator master).')

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
        setor_destino=setor_entrada,
        quantidade=q_ent,
        valor_unitario=p_ent,
        valor_custo_medio_apos=custo_novo,
        nota_item=item,
        usuario=usuario,
        observacao=(
            f'NF {item.nota_fiscal.numero_nota}'
            + (f' · {det_conv}' if det_conv else '')
        ),
    )

    return EntradaEstoqueNota.objects.create(
        nota_item=item,
        produto=produto,
        quantidade=q_ent,
        valor_unitario=p_ent,
        marca=(marca or produto.marca or '')[:120],
        unidade_master=(unidade_master or produto.unidade_master or '')[:20],
        quantidade_por_master=produto.quantidade_por_master or Decimal('0'),
        data_validade=data_validade,
        movimento=mov,
        criado_por=usuario,
    )


def _motivo_bloqueio_estorno_entrada(entrada: EntradaEstoqueNota) -> str:
    produto = entrada.produto
    q_ent = entrada.quantidade or Decimal('0')
    saldo = produto.quantidade_estoque or Decimal('0')
    if saldo < q_ent:
        return (
            f'Saldo insuficiente na farmácia/patrimônio ({saldo}) para estornar {q_ent}. '
            'Já houve saída ou transferência deste produto.'
        )
    outros = MovimentoEstoque.objects.filter(produto=produto).exclude(
        pk=entrada.movimento_id,
    )
    if outros.filter(
        tipo__in=(
            MovimentoEstoque.Tipo.TRANSFERENCIA,
            MovimentoEstoque.Tipo.BAIXA,
            MovimentoEstoque.Tipo.AJUSTE,
        ),
    ).exists():
        return 'Não é possível estornar: existem transferências, baixas ou ajustes após esta entrada.'
    if SaldoEstoqueSetor.objects.filter(produto=produto).exclude(quantidade=0).exists():
        return 'Não é possível estornar: ainda há saldo em setores (material já distribuído).'
    return ''


def pode_estornar_entrada_nota(entrada: EntradaEstoqueNota) -> bool:
    return not _motivo_bloqueio_estorno_entrada(entrada)


@transaction.atomic
def estornar_entrada_desde_item_nota(
    item: NotaFiscalEntradaItem,
    *,
    usuario,
) -> None:
    entrada = (
        EntradaEstoqueNota.objects.filter(nota_item=item)
        .select_related('produto', 'movimento')
        .first()
    )
    if not entrada:
        raise EstoqueErro('Este item não possui entrada de estoque para estornar.')

    bloqueio = _motivo_bloqueio_estorno_entrada(entrada)
    if bloqueio:
        raise EstoqueErro(bloqueio)

    produto = entrada.produto
    q_ent = entrada.quantidade or Decimal('0')
    p_ent = entrada.valor_unitario or Decimal('0')
    q_depois = produto.quantidade_estoque or Decimal('0')
    c_depois = produto.valor_custo_medio or Decimal('0')
    q_antes = q_depois - q_ent

    if q_antes > 0:
        c_antes = (q_depois * c_depois - q_ent * p_ent) / q_antes
    else:
        c_antes = Decimal('0')

    produto.quantidade_estoque = q_antes
    produto.valor_custo_medio = c_antes
    if q_antes <= 0:
        produto.valor_ultima_compra = Decimal('0')
    produto.save(update_fields=['quantidade_estoque', 'valor_custo_medio', 'valor_ultima_compra', 'atualizado_em'])

    mov_id = entrada.movimento_id
    produto_id = produto.pk
    entrada.delete()
    if mov_id:
        MovimentoEstoque.objects.filter(pk=mov_id).delete()

    restantes = EntradaEstoqueNota.objects.filter(produto_id=produto_id).exists()
    tem_mov = MovimentoEstoque.objects.filter(produto_id=produto_id).exists()
    if q_antes <= 0 and not restantes and not tem_mov:
        ProdutoEstoque.objects.filter(pk=produto_id).delete()


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
