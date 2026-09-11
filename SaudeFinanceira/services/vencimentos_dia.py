"""Despesas com vencimento no dia (planejamento + contas a pagar)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.urls import reverse

SESSION_POPUP_VENCIMENTOS = 'mostrar_popup_vencimentos_dia'


@dataclass
class DespesaVencimentoDia:
    origem: str
    origem_label: str
    nome: str
    valor: Decimal
    categoria: str
    url: str
    detalhe: str = ''


def marcar_popup_vencimentos_dia(request) -> None:
    request.session[SESSION_POPUP_VENCIMENTOS] = True


def despesas_vencendo_hoje(empresa_id: int, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    itens: list[DespesaVencimentoDia] = []
    itens.extend(_planejamento_vencendo_hoje(empresa_id, hoje))
    itens.extend(_contas_pagar_vencendo_hoje(empresa_id, hoje))
    itens.sort(key=lambda x: (x.origem, x.nome.lower()))
    total = sum((i.valor for i in itens), Decimal('0'))
    return {
        'itens': itens,
        'total': total,
        'data': hoje,
        'quantidade': len(itens),
    }


def _planejamento_vencendo_hoje(empresa_id: int, hoje: date) -> list[DespesaVencimentoDia]:
    from planejamento_orcamentario.models import ItemOrcamento, LancamentoOrcamento

    lancamentos = (
        LancamentoOrcamento.objects.filter(
            empresa_id=empresa_id,
            data_lancamento=hoje,
            item__ativo=True,
        )
        .exclude(item__tipo=ItemOrcamento.TIPO_RECEITA)
        .select_related('item', 'item__categoria')
        .order_by('item__nome')
    )
    itens = []
    for lanc in lancamentos:
        item = lanc.item
        itens.append(
            DespesaVencimentoDia(
                origem='planejamento',
                origem_label='Planejamento',
                nome=item.nome,
                valor=lanc.valor or Decimal('0'),
                categoria=item.categoria.nome if item.categoria else '',
                url=reverse('planejamento_orcamentario:listar_tipo', args=[item.tipo]),
                detalhe=item.get_tipo_display(),
            )
        )
    return itens


def _contas_pagar_vencendo_hoje(empresa_id: int, hoje: date) -> list[DespesaVencimentoDia]:
    from contasapagar.models import ContasaPagar

    contas = (
        ContasaPagar.objects.filter(
            empresa_id=empresa_id,
            dtvenc=hoje,
            status__in=('pendente', 'vencido'),
        )
        .select_related('fornecedor', 'categoria')
        .order_by('descricao', 'fornecedor__razao')
    )
    itens = []
    for conta in contas:
        fornecedor = str(conta.fornecedor) if conta.fornecedor_id else ''
        itens.append(
            DespesaVencimentoDia(
                origem='contas_pagar',
                origem_label='Contas a pagar',
                nome=conta.descricao or fornecedor or 'Conta a pagar',
                valor=conta.get_valor_pendente(),
                categoria=conta.categoria.nome if conta.categoria_id else '',
                url=reverse('contasapagar:editar', args=[conta.pk]),
                detalhe=fornecedor,
            )
        )
    return itens
