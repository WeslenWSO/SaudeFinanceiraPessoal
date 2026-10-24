"""Evolução histórica do faturamento (aba Análises — período até 12 meses)."""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Q

from faturamento_medico.dashboard_exames import STATUS_AGENDAMENTO_CANCELADOS
from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.ranking_exames import montar_ranking_exames_qs

MESES_ABREV = (
    '',
    'jan',
    'fev',
    'mar',
    'abr',
    'mai',
    'jun',
    'jul',
    'ago',
    'set',
    'out',
    'nov',
    'dez',
)

MAX_MESES_EVOLUCAO = 12


def _q_cancelados():
    q = Q()
    for status in STATUS_AGENDAMENTO_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _fmt_moeda(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return 'R$ 0,00'
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {s}'


def _fmt_mes_ano_curto(ano: int, mes: int) -> str:
    abrev = MESES_ABREV[mes] if 1 <= mes <= 12 else '???'
    return f'{abrev}/{ano % 100:02d}'


def _parse_ano_mes(texto: str | None) -> tuple[int, int] | None:
    texto = (texto or '').strip()
    if len(texto) != 7 or texto[4] != '-':
        return None
    try:
        ano = int(texto[:4])
        mes = int(texto[5:7])
    except ValueError:
        return None
    if mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
        return None
    return ano, mes


def resolver_periodo_evolucao(
    request,
    *,
    ano_ref: int,
    mes_ref: int,
) -> tuple[int, int, int, int, str | None]:
    """
    Retorna (ano_de, mes_de, ano_ate, mes_ate, aviso).
    Intervalo inclusivo, no máximo MAX_MESES_EVOLUCAO meses.
    """
    def _param(nome: str) -> str | None:
        return request.GET.get(nome) or request.POST.get(nome)

    ate = _parse_ano_mes(_param('ev_ate')) or _parse_ano_mes(_param('mes'))
    if not ate:
        ate = (ano_ref, mes_ref)

    de = _parse_ano_mes(_param('ev_de'))
    if not de:
        ref_ate = date(ate[0], ate[1], 1)
        ref_de = ref_ate - relativedelta(months=MAX_MESES_EVOLUCAO - 1)
        de = (ref_de.year, ref_de.month)

    ano_de, mes_de = de
    ano_ate, mes_ate = ate
    aviso: str | None = None

    if date(ano_de, mes_de, 1) > date(ano_ate, mes_ate, 1):
        ano_de, mes_de, ano_ate, mes_ate = ano_ate, mes_ate, ano_de, mes_de
        aviso = 'Datas invertidas; período ajustado.'

    inicio = date(ano_de, mes_de, 1)
    fim = date(ano_ate, mes_ate, 1)
    meses = (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1
    if meses > MAX_MESES_EVOLUCAO:
        inicio = fim - relativedelta(months=MAX_MESES_EVOLUCAO - 1)
        ano_de, mes_de = inicio.year, inicio.month
        aviso = f'Período limitado a {MAX_MESES_EVOLUCAO} meses; intervalo ajustado.'

    return ano_de, mes_de, ano_ate, mes_ate, aviso


def _iter_meses(ano_de: int, mes_de: int, ano_ate: int, mes_ate: int):
    cur = date(ano_de, mes_de, 1)
    fim = date(ano_ate, mes_ate, 1)
    while cur <= fim:
        yield cur.year, cur.month
        cur += relativedelta(months=1)


def montar_evolucao_faturamento(
    empresa_id: int,
    ano_de: int,
    mes_de: int,
    ano_ate: int,
    mes_ate: int,
) -> dict:
    linhas: list[dict] = []
    valor_anterior: Decimal | None = None

    for ano, mes in _iter_meses(ano_de, mes_de, ano_ate, mes_ate):
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, monthrange(ano, mes)[1])
        qs = (
            FaturamentoMedico.objects.filter(
                empresa_id=empresa_id,
                data__gte=inicio,
                data__lte=fim,
            )
            .exclude(_q_cancelados())
        )
        dias = qs.values('data').distinct().count()
        ranking = montar_ranking_exames_qs(qs)
        valor = ranking['total_valor']
        rs_dia = (valor / dias) if dias else Decimal('0')

        if valor_anterior is not None and valor_anterior != 0:
            pct = ((valor / valor_anterior) - Decimal('1')) * Decimal('100')
            variacao_fmt = f'{pct:.1f}'.replace('.', ',') + '%'
        else:
            variacao_fmt = '—'

        linhas.append({
            'mes_ano_fmt': _fmt_mes_ano_curto(ano, mes),
            'dias_trabalhados': dias,
            'dias_trabalhados_fmt': str(dias),
            'valor': float(valor),
            'rs_dia': float(rs_dia),
            'faturamento_fmt': _fmt_moeda(valor),
            'rs_dia_fmt': _fmt_moeda(rs_dia),
            'variacao_fmt': variacao_fmt,
        })
        valor_anterior = valor

    rotulo_de = _fmt_mes_ano_curto(ano_de, mes_de)
    rotulo_ate = _fmt_mes_ano_curto(ano_ate, mes_ate)
    subtitulo = f'{rotulo_de} a {rotulo_ate}'
    chart_labels = [linha['mes_ano_fmt'] for linha in linhas]
    chart_valores = [linha['valor'] for linha in linhas]
    chart_rs_dia = [linha['rs_dia'] for linha in linhas]
    chart_dias = [linha['dias_trabalhados'] for linha in linhas]
    chart_labels_dias = [f'{d} dias' for d in chart_dias]
    return {
        'titulo_relatorio': 'EVOLUÇÃO HISTÓRICA DO FATURAMENTO',
        'subtitulo_periodo': subtitulo,
        'titulo_grafico': f'Faturamento Bruto Mensal — {subtitulo}',
        'titulo_grafico_rs_dia': f'Faturamento Bruto Médio Diário/Mês — {subtitulo}',
        'linhas_evolucao': linhas,
        'ev_periodo_de_value': f'{ano_de:04d}-{mes_de:02d}',
        'ev_periodo_ate_value': f'{ano_ate:04d}-{mes_ate:02d}',
        'chart_evolucao_labels_json': json.dumps(chart_labels, ensure_ascii=False),
        'chart_evolucao_valores_json': json.dumps(chart_valores),
        'chart_evolucao_rs_dia_json': json.dumps(chart_rs_dia),
        'chart_evolucao_dias_json': json.dumps(chart_dias),
        'chart_evolucao_labels_dias_json': json.dumps(chart_labels_dias, ensure_ascii=False),
    }
