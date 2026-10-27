"""Indicadores gerenciais de estoque por empresa."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.fields import DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from estoque.alertas import contar_abaixo_estoque_minimo, queryset_abaixo_estoque_minimo
from estoque.models import MovimentoEstoque, NaturezaEstoque, ProdutoEstoque, RequisicaoEstoque


def _fmt_moeda(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return '0,00'
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s


def _fmt_numero(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return '0'
    if v == v.to_integral_value():
        return f'{int(v):,}'.replace(',', '.')
    s = f'{v:,.3f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s.rstrip('0').rstrip(',')


def _valor_linha_custo_medio():
    return Coalesce(F('quantidade_estoque'), Decimal('0')) * Coalesce(
        F('valor_custo_medio'), Decimal('0')
    )


def _valor_linha_custo_contabil():
    return Coalesce(F('quantidade_estoque_contabil'), Decimal('0')) * Coalesce(
        F('valor_custo_contabil'), Decimal('0')
    )


def _periodo_mes(ref: date | None = None) -> tuple[date, date]:
    hoje = ref or timezone.localdate()
    ini = hoje.replace(day=1)
    fim = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    return ini, fim


def montar_kpis_estoque(empresa_id: int | None, *, ref: date | None = None) -> dict:
    vazio = {
        'empresa_id': empresa_id,
        'periodo_inicio': None,
        'periodo_fim': None,
        'periodo_rotulo': '',
        'farmacia_produtos': 0,
        'farmacia_com_saldo': 0,
        'abaixo_minimo': 0,
        'valor_farmacia_medio_fmt': '0,00',
        'valor_farmacia_contabil_fmt': '0,00',
        'imobilizado_itens': 0,
        'valor_imobilizado_fmt': '0,00',
        'requisicoes_rascunho': 0,
        'requisicoes_mes': 0,
        'mov_entradas_mes': 0,
        'mov_baixas_mes': 0,
        'mov_transferencias_mes': 0,
        'mov_ajustes_mes': 0,
        'inventarios_abertos': 0,
        'alertas_amostra': [],
        'top_baixas_mes': [],
    }
    if not empresa_id:
        return vazio

    ini, fim = _periodo_mes(ref)
    dec = DecimalField(max_digits=18, decimal_places=2)

    qs_farm = ProdutoEstoque.objects.filter(
        empresa_id=empresa_id,
        natureza=NaturezaEstoque.CONSUMIVEL,
    )
    qs_imob = ProdutoEstoque.objects.filter(
        empresa_id=empresa_id,
        natureza=NaturezaEstoque.IMOBILIZADO,
    )

    agg_farm = qs_farm.aggregate(
        total=Count('id'),
        com_saldo=Count('id', filter=Q(quantidade_estoque__gt=0)),
        valor_medio=Sum(_valor_linha_custo_medio(), output_field=dec),
        valor_contabil=Sum(_valor_linha_custo_contabil(), output_field=dec),
    )
    agg_imob = qs_imob.aggregate(
        total=Count('id'),
        valor=Sum(_valor_linha_custo_medio(), output_field=dec),
    )

    movs = MovimentoEstoque.objects.filter(
        empresa_id=empresa_id,
        criado_em__date__gte=ini,
        criado_em__date__lte=fim,
    )
    mov_por_tipo = {
        row['tipo']: row['n']
        for row in movs.values('tipo').annotate(n=Count('id'))
    }

    top_baixas = (
        movs.filter(tipo=MovimentoEstoque.Tipo.BAIXA)
        .values('produto__codigo_produto', 'produto__descricao')
        .annotate(total=Sum('quantidade'))
        .order_by('-total')[:8]
    )

    try:
        from inventario.models import Inventario

        inv_abertos = Inventario.objects.filter(
            empresa_id=empresa_id,
            aberto=True,
            estoque_aplicado_em__isnull=True,
        ).count()
    except Exception:
        inv_abertos = 0

    alertas = list(
        queryset_abaixo_estoque_minimo(empresa_id).values(
            'codigo_produto',
            'descricao',
            'quantidade_estoque',
            'estoque_minimo',
        )[:10]
    )

    mes_nome = ini.strftime('%m/%Y')

    return {
        'empresa_id': empresa_id,
        'periodo_inicio': ini,
        'periodo_fim': fim,
        'periodo_rotulo': mes_nome,
        'farmacia_produtos': agg_farm['total'] or 0,
        'farmacia_com_saldo': agg_farm['com_saldo'] or 0,
        'abaixo_minimo': contar_abaixo_estoque_minimo(empresa_id),
        'valor_farmacia_medio_fmt': _fmt_moeda(agg_farm['valor_medio']),
        'valor_farmacia_contabil_fmt': _fmt_moeda(agg_farm['valor_contabil']),
        'imobilizado_itens': agg_imob['total'] or 0,
        'valor_imobilizado_fmt': _fmt_moeda(agg_imob['valor']),
        'requisicoes_rascunho': RequisicaoEstoque.objects.filter(
            empresa_id=empresa_id,
            status=RequisicaoEstoque.Status.RASCUNHO,
        ).count(),
        'requisicoes_mes': RequisicaoEstoque.objects.filter(
            empresa_id=empresa_id,
            status=RequisicaoEstoque.Status.CONCLUIDA,
            concluida_em__date__gte=ini,
            concluida_em__date__lte=fim,
        ).count(),
        'mov_entradas_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.ENTRADA_NF, 0),
        'mov_baixas_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.BAIXA, 0),
        'mov_transferencias_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.TRANSFERENCIA, 0),
        'mov_ajustes_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.AJUSTE, 0),
        'inventarios_abertos': inv_abertos,
        'alertas_amostra': alertas,
        'top_baixas_mes': [
            {
                'codigo': row['produto__codigo_produto'],
                'descricao': row['produto__descricao'],
                'total_fmt': _fmt_numero(row['total']),
            }
            for row in top_baixas
        ],
    }
