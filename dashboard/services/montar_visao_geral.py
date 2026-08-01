"""Agregações para o dashboard principal — Visão Geral."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber

MESES_CURTO = ('Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez')

REGIMES = (
    ('geral', 'Visão Geral'),
    ('competencia', 'Competência'),
    ('caixa', 'Caixa Realizado'),
)

SUFIXO_REGIME = {
    'geral': 'visão geral',
    'competencia': 'competência',
    'caixa': 'caixa realizado',
}


def _cap_empresa_q(empresa):
    return Q(empresa=empresa) | Q(empresa__isnull=True, fornecedor__empresa=empresa)


def _clip_mes(data_inicio: date, data_fim: date, ano: int, mes: int) -> tuple[date, date]:
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, monthrange(ano, mes)[1])
    return max(primeiro, data_inicio), min(ultimo, data_fim)


def _iter_meses(data_inicio: date, data_fim: date):
    ano, mes = data_inicio.year, data_inicio.month
    fim_ano, fim_mes = data_fim.year, data_fim.month
    while (ano, mes) <= (fim_ano, fim_mes):
        ini, fim = _clip_mes(data_inicio, data_fim, ano, mes)
        yield ano, mes, ini, fim
        if mes == 12:
            ano, mes = ano + 1, 1
        else:
            mes += 1


def _sum_receitas_caixa(empresa, ini: date, fim: date) -> Decimal:
    return ContaAReceber.objects.filter(
        empresa=empresa,
        status='pago',
        data_recebimento__gte=ini,
        data_recebimento__lte=fim,
    ).aggregate(t=Coalesce(Sum('valor_recebido'), Decimal('0')))['t'] or Decimal('0')


def _sum_receitas_competencia(empresa, ini: date, fim: date) -> Decimal:
    return ContaAReceber.objects.filter(
        empresa=empresa,
        data_emissao__gte=ini,
        data_emissao__lte=fim,
    ).exclude(status='cancelado').aggregate(
        t=Coalesce(Sum('valor_a_receber'), Decimal('0')),
    )['t'] or Decimal('0')


def _sum_receitas_geral(empresa, ini: date, fim: date) -> Decimal:
    pago = _sum_receitas_caixa(empresa, ini, fim)
    aberto = ContaAReceber.objects.filter(
        empresa=empresa,
        data_vencimento__gte=ini,
        data_vencimento__lte=fim,
    ).exclude(status__in=['pago', 'cancelado']).aggregate(
        t=Coalesce(Sum('valor_a_receber'), Decimal('0')),
    )['t'] or Decimal('0')
    return pago + aberto


def _sum_despesas_caixa(empresa, ini: date, fim: date) -> Decimal:
    return ContasaPagar.objects.filter(
        _cap_empresa_q(empresa),
        dtPag__gte=ini,
        dtPag__lte=fim,
        valorPago__gt=0,
        categoria__tipo='D',
    ).exclude(status='cancelado').aggregate(
        t=Coalesce(Sum('valorPago'), Decimal('0')),
    )['t'] or Decimal('0')


def _sum_despesas_competencia(empresa, ini: date, fim: date) -> Decimal:
    base = ContasaPagar.objects.filter(
        _cap_empresa_q(empresa),
        categoria__tipo='D',
    ).exclude(status='cancelado')
    com_emissao = base.filter(
        dtEmissao__gte=ini,
        dtEmissao__lte=fim,
    ).aggregate(t=Coalesce(Sum('valorDoc'), Decimal('0')))['t'] or Decimal('0')
    sem_emissao = base.filter(dtEmissao__isnull=True, dtvenc__gte=ini, dtvenc__lte=fim).aggregate(
        t=Coalesce(Sum('valorDoc'), Decimal('0')),
    )['t'] or Decimal('0')
    return com_emissao + sem_emissao


def _sum_despesas_geral(empresa, ini: date, fim: date) -> Decimal:
    pago = _sum_despesas_caixa(empresa, ini, fim)
    aberto = ContasaPagar.objects.filter(
        _cap_empresa_q(empresa),
        dtvenc__gte=ini,
        dtvenc__lte=fim,
        categoria__tipo='D',
    ).filter(Q(valorPago__isnull=True) | Q(valorPago=0)).exclude(
        status__in=['pago', 'cancelado'],
    ).aggregate(t=Coalesce(Sum('valorDoc'), Decimal('0')))['t'] or Decimal('0')
    return pago + aberto


def _receitas_por_categoria(empresa, ini: date, fim: date, regime: str, limite: int = 10):
    if regime == 'caixa':
        qs = (
            ContaAReceber.objects.filter(
                empresa=empresa,
                status='pago',
                data_recebimento__gte=ini,
                data_recebimento__lte=fim,
                categoria__isnull=False,
            )
            .values('categoria__nome')
            .annotate(total=Coalesce(Sum('valor_recebido'), Decimal('0')))
            .order_by('-total')[:limite]
        )
    elif regime == 'competencia':
        qs = (
            ContaAReceber.objects.filter(
                empresa=empresa,
                data_emissao__gte=ini,
                data_emissao__lte=fim,
                categoria__isnull=False,
            )
            .exclude(status='cancelado')
            .values('categoria__nome')
            .annotate(total=Coalesce(Sum('valor_a_receber'), Decimal('0')))
            .order_by('-total')[:limite]
        )
    else:
        qs_pago = (
            ContaAReceber.objects.filter(
                empresa=empresa,
                status='pago',
                data_recebimento__gte=ini,
                data_recebimento__lte=fim,
                categoria__isnull=False,
            )
            .values('categoria_id', 'categoria__nome')
            .annotate(total=Coalesce(Sum('valor_recebido'), Decimal('0')))
        )
        qs_aberto = (
            ContaAReceber.objects.filter(
                empresa=empresa,
                data_vencimento__gte=ini,
                data_vencimento__lte=fim,
                categoria__isnull=False,
            )
            .exclude(status__in=['pago', 'cancelado'])
            .values('categoria_id', 'categoria__nome')
            .annotate(total=Coalesce(Sum('valor_a_receber'), Decimal('0')))
        )
        totais: dict[int, dict] = {}
        for row in list(qs_pago) + list(qs_aberto):
            cid = row['categoria_id']
            if cid not in totais:
                totais[cid] = {'nome': row['categoria__nome'] or '—', 'total': Decimal('0')}
            totais[cid]['total'] += row['total'] or Decimal('0')
        ordenado = sorted(totais.values(), key=lambda x: x['total'], reverse=True)[:limite]
        return [{'nome': x['nome'], 'total': x['total']} for x in ordenado]

    return [{'nome': r['categoria__nome'] or '—', 'total': r['total'] or Decimal('0')} for r in qs]


def _despesas_por_categoria(empresa, ini: date, fim: date, regime: str, limite: int = 10):
    base = ContasaPagar.objects.filter(
        _cap_empresa_q(empresa),
        categoria__tipo='D',
        categoria__isnull=False,
    ).exclude(status='cancelado')

    if regime == 'caixa':
        qs = (
            base.filter(dtPag__gte=ini, dtPag__lte=fim, valorPago__gt=0)
            .values('categoria__nome')
            .annotate(total=Coalesce(Sum('valorPago'), Decimal('0')))
            .order_by('-total')[:limite]
        )
    elif regime == 'competencia':
        qs_em = (
            base.filter(dtEmissao__gte=ini, dtEmissao__lte=fim)
            .values('categoria_id', 'categoria__nome')
            .annotate(total=Coalesce(Sum('valorDoc'), Decimal('0')))
        )
        qs_venc = (
            base.filter(dtEmissao__isnull=True, dtvenc__gte=ini, dtvenc__lte=fim)
            .values('categoria_id', 'categoria__nome')
            .annotate(total=Coalesce(Sum('valorDoc'), Decimal('0')))
        )
        totais: dict[int, dict] = {}
        for row in list(qs_em) + list(qs_venc):
            cid = row['categoria_id']
            if cid not in totais:
                totais[cid] = {'nome': row['categoria__nome'] or '—', 'total': Decimal('0')}
            totais[cid]['total'] += row['total'] or Decimal('0')
        ordenado = sorted(totais.values(), key=lambda x: x['total'], reverse=True)[:limite]
        return [{'nome': x['nome'], 'total': x['total']} for x in ordenado]
    else:
        qs_pago = (
            base.filter(dtPag__gte=ini, dtPag__lte=fim, valorPago__gt=0)
            .values('categoria_id', 'categoria__nome')
            .annotate(total=Coalesce(Sum('valorPago'), Decimal('0')))
        )
        qs_aberto = (
            base.filter(dtvenc__gte=ini, dtvenc__lte=fim)
            .filter(Q(valorPago__isnull=True) | Q(valorPago=0))
            .exclude(status='pago')
            .values('categoria_id', 'categoria__nome')
            .annotate(total=Coalesce(Sum('valorDoc'), Decimal('0')))
        )
        totais = {}
        for row in list(qs_pago) + list(qs_aberto):
            cid = row['categoria_id']
            if cid not in totais:
                totais[cid] = {'nome': row['categoria__nome'] or '—', 'total': Decimal('0')}
            totais[cid]['total'] += row['total'] or Decimal('0')
        ordenado = sorted(totais.values(), key=lambda x: x['total'], reverse=True)[:limite]
        return [{'nome': x['nome'], 'total': x['total']} for x in ordenado]

    return [{'nome': r['categoria__nome'] or '—', 'total': r['total'] or Decimal('0')} for r in qs]


def _contas_a_vencer(empresa) -> tuple[Decimal, Decimal]:
    """Saldo pendente a receber e a pagar (todas as contas em aberto)."""
    a_receber = Decimal('0')
    for car in ContaAReceber.objects.filter(
        empresa=empresa,
        status__in=['pendente', 'vencido', 'cartao'],
    ).only('valor_a_receber', 'valor_recebido', 'desconto', 'tarifas', 'juros', 'status'):
        a_receber += car.get_valor_pendente()

    a_pagar = Decimal('0')
    for cap in ContasaPagar.objects.filter(
        _cap_empresa_q(empresa),
        status__in=['pendente', 'vencido'],
    ).select_related('categoria'):
        a_pagar += cap.get_valor_pendente()

    return a_receber, a_pagar


def montar_visao_geral(empresa, data_inicio: date, data_fim: date, regime: str = 'geral') -> dict:
    if regime not in {r[0] for r in REGIMES}:
        regime = 'geral'

    sum_rec_fn = {
        'geral': _sum_receitas_geral,
        'competencia': _sum_receitas_competencia,
        'caixa': _sum_receitas_caixa,
    }[regime]
    sum_desp_fn = {
        'geral': _sum_despesas_geral,
        'competencia': _sum_despesas_competencia,
        'caixa': _sum_despesas_caixa,
    }[regime]

    labels = []
    receitas_mes = []
    despesas_mes = []
    for ano, mes, ini, fim in _iter_meses(data_inicio, data_fim):
        labels.append(f'{MESES_CURTO[mes - 1]} {ano}')
        receitas_mes.append(float(sum_rec_fn(empresa, ini, fim)))
        despesas_mes.append(float(sum_desp_fn(empresa, ini, fim)))

    entradas = _receitas_por_categoria(empresa, data_inicio, data_fim, regime)
    saidas = _despesas_por_categoria(empresa, data_inicio, data_fim, regime)
    total_receber, total_pagar = _contas_a_vencer(empresa)

    sufixo = SUFIXO_REGIME[regime]
    leg_rec = f'Receitas Totais ({sufixo})'
    leg_desp = f'Custos/Despesas Totais ({sufixo})'

    return {
        'regime': regime,
        'legenda_receitas': leg_rec,
        'legenda_despesas': leg_desp,
        'total_receitas_periodo': sum(receitas_mes),
        'total_despesas_periodo': sum(despesas_mes),
        'contas_receber': total_receber,
        'contas_pagar': total_pagar,
        'entradas_categoria': entradas,
        'saidas_categoria': saidas,
        'chart_mensal_labels_json': json.dumps(labels, ensure_ascii=False),
        'chart_mensal_receitas_json': json.dumps(receitas_mes),
        'chart_mensal_despesas_json': json.dumps(despesas_mes),
        'chart_vencer_labels_json': json.dumps(['Receber', 'Pagar'], ensure_ascii=False),
        'chart_vencer_data_json': json.dumps([float(total_receber), float(total_pagar)]),
        'chart_entradas_labels_json': json.dumps([e['nome'] for e in entradas], ensure_ascii=False),
        'chart_entradas_data_json': json.dumps([float(e['total']) for e in entradas]),
        'chart_saidas_labels_json': json.dumps([s['nome'] for s in saidas], ensure_ascii=False),
        'chart_saidas_data_json': json.dumps([float(s['total']) for s in saidas]),
        'tem_dados': any(receitas_mes) or any(despesas_mes) or entradas or saidas,
    }
