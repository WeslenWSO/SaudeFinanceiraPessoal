"""Dashboard analítico Conta Azul por tipos R/D/I/L."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber

TIPOS_DESPESA = (
    ('D', 'Despesas', 'danger'),
    ('I', 'Investimento', 'warning'),
    ('L', 'Distribuição de Lucro', 'dark'),
)


def _qs_receitas_ca(empresa, data_inicio: date, data_fim: date):
    return ContaAReceber.objects.filter(
        empresa=empresa,
        data_vencimento__gte=data_inicio,
        data_vencimento__lte=data_fim,
    ).exclude(conta_azul_parcela_id='')


def _qs_despesas_ca(empresa, data_inicio: date, data_fim: date, tipo: str | None = None):
    qs = ContasaPagar.objects.filter(
        empresa=empresa,
        dtvenc__gte=data_inicio,
        dtvenc__lte=data_fim,
    ).exclude(conta_azul_parcela_id='')
    if tipo:
        qs = qs.filter(categoria__tipo=tipo)
    return qs


def _nome_grupo(grupo: str | None) -> str:
    return (grupo or '').strip() or 'Sem grupo'


def montar_dashboard_por_tipo(empresa, data_inicio: date, data_fim: date) -> dict:
    qs_rec = _qs_receitas_ca(empresa, data_inicio, data_fim)

    total_receitas = qs_rec.aggregate(
        t=Coalesce(Sum('valor_a_receber'), Decimal('0')),
    )['t'] or Decimal('0')

    totais_tipo: dict[str, Decimal] = {}
    blocos = []

    for cod, rotulo, cor in TIPOS_DESPESA:
        qs = _qs_despesas_ca(empresa, data_inicio, data_fim, cod)
        total = qs.aggregate(t=Coalesce(Sum('valorDoc'), Decimal('0')))['t'] or Decimal('0')
        totais_tipo[cod] = total

        por_grupo = list(
            qs.filter(categoria__isnull=False)
            .values('categoria__grupo')
            .annotate(
                total=Coalesce(Sum('valorDoc'), Decimal('0')),
                qtd=Count('id'),
            )
            .order_by('-total')
        )
        grupos = [
            {
                'nome': _nome_grupo(g['categoria__grupo']),
                'total': g['total'] or Decimal('0'),
                'qtd': g['qtd'] or 0,
            }
            for g in por_grupo
        ]

        por_categoria = list(
            qs.filter(categoria__isnull=False)
            .values('categoria__nome', 'categoria__grupo', 'categoria__classificacao')
            .annotate(total=Coalesce(Sum('valorDoc'), Decimal('0')))
            .order_by('-total')[:15]
        )
        categorias = [
            {
                'nome': c['categoria__nome'] or '—',
                'grupo': _nome_grupo(c['categoria__grupo']),
                'classificacao': c['categoria__classificacao'] or '',
                'total': c['total'] or Decimal('0'),
            }
            for c in por_categoria
        ]

        blocos.append({
            'codigo': cod,
            'rotulo': rotulo,
            'cor': cor,
            'total': total,
            'grupos': grupos,
            'categorias': categorias,
        })

    total_despesas = totais_tipo.get('D', Decimal('0'))
    total_investimento = totais_tipo.get('I', Decimal('0'))
    total_lucro = totais_tipo.get('L', Decimal('0'))
    resultado = total_receitas - total_despesas - total_investimento - total_lucro

    receitas_grupo = list(
        qs_rec.filter(categoria__isnull=False)
        .values('categoria__grupo')
        .annotate(
            total=Coalesce(Sum('valor_a_receber'), Decimal('0')),
            qtd=Count('id'),
        )
        .order_by('-total')
    )
    receitas_grupos = [
        {
            'nome': _nome_grupo(g['categoria__grupo']),
            'total': g['total'] or Decimal('0'),
            'qtd': g['qtd'] or 0,
        }
        for g in receitas_grupo
    ]

    chart_labels = ['Receitas', 'Despesas', 'Investimento', 'Dist. Lucro']
    chart_data = [
        float(total_receitas),
        float(total_despesas),
        float(total_investimento),
        float(total_lucro),
    ]

    return {
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'total_investimento': total_investimento,
        'total_lucro': total_lucro,
        'resultado': resultado,
        'receitas_grupos': receitas_grupos,
        'blocos': blocos,
        'chart_tipo_labels_json': json.dumps(chart_labels, ensure_ascii=False),
        'chart_tipo_data_json': json.dumps(chart_data),
        'chart_tipo_cores_json': json.dumps(['#198754', '#dc3545', '#ffc107', '#212529']),
    }
