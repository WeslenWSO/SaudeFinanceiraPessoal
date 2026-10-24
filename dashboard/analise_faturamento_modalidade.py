"""Relatório mensal de faturamento por modalidade (aba Análises)."""
from __future__ import annotations

import json
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from faturamento_medico.dashboard_exames import MESES_PT
from faturamento_medico.lote_relatorio import _modalidade_item, _normalizar_codigo_modalidade
from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.ranking_exames import _valor_item

from dashboard.analise_faturamento_convenio import (
    _fmt_moeda,
    _fmt_numero_int,
    _q_cancelados,
)
from dashboard.analises_agendamento import (
    LEGENDA_FILTRO_ANALISES,
    agendamento_conta_faturamento_analises,
)

ROTULOS_MODALIDADE = {
    'MR': 'Ressonância Magnética',
    'CT': 'Tomografia',
    'US': 'Ultrassonografia',
    'MG': 'Mamografia',
    'CR': 'Raio-X',
    'EC': 'Eletrocardiograma',
    'EG': 'Eletroencefalograma',
}

CORES_MODALIDADE = {
    'MR': '#4472C4',
    'CT': '#70AD47',
    'US': '#9DC3E6',
    'MG': '#FFC000',
    'CR': '#C55A11',
    'EC': '#7030A0',
    'EG': '#ED7D31',
}


def _codigo_modalidade(faturamento, item) -> str:
    bruto = (_modalidade_item(faturamento, item) or '').strip().upper()
    if bruto == 'RX':
        bruto = 'CR'
    if bruto in ROTULOS_MODALIDADE:
        return bruto
    cod = _normalizar_codigo_modalidade(bruto)
    if cod in ROTULOS_MODALIDADE:
        return cod
    if len(bruto) <= 4 and bruto.isalpha():
        return bruto
    return 'OUTROS'


def _rotulo_modalidade(codigo: str) -> str:
    return ROTULOS_MODALIDADE.get(codigo, 'Outros')


def _fmt_percentual_1(parte, total) -> str:
    try:
        p = Decimal(str(parte or 0))
        t = Decimal(str(total or 0))
    except Exception:
        return '0,0%'
    if not t:
        return '0,0%'
    pct = (p / t) * Decimal('100')
    return f'{pct:.1f}'.replace('.', ',') + '%'


def montar_relatorio_faturamento_modalidade(empresa_id: int, ano: int, mes: int) -> dict:
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])

    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=inicio,
            data__lte=fim,
        )
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )

    por_mod: dict[str, dict] = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})

    for fat in qs:
        if not agendamento_conta_faturamento_analises(fat):
            continue
        itens = list(fat.itens_servico.all())
        if not itens:
            cod = _codigo_modalidade(fat, None)
            por_mod[cod]['quantidade'] += 1
            por_mod[cod]['valor'] += _valor_item(None, fat)
            continue
        for item in itens:
            cod = _codigo_modalidade(fat, item)
            por_mod[cod]['quantidade'] += 1
            por_mod[cod]['valor'] += _valor_item(item, fat)

    linhas_raw = sorted(
        por_mod.items(),
        key=lambda x: (-float(x[1]['valor']), -x[1]['quantidade'], _rotulo_modalidade(x[0])),
    )

    total_qtd = sum(d['quantidade'] for _, d in linhas_raw)
    total_valor = sum((d['valor'] for _, d in linhas_raw), Decimal('0'))
    ticket_geral = (total_valor / total_qtd) if total_qtd else Decimal('0')

    linhas = []
    chart_labels = []
    chart_faturamento = []
    chart_ticket = []
    chart_cores = []

    for codigo, dados in linhas_raw:
        qtd = dados['quantidade']
        valor = dados['valor']
        ticket = (valor / qtd) if qtd else Decimal('0')
        rotulo = _rotulo_modalidade(codigo)
        cor = CORES_MODALIDADE.get(codigo, '#6c757d')
        linhas.append({
            'modalidade': rotulo,
            'quantidade': qtd,
            'quantidade_fmt': _fmt_numero_int(qtd),
            'valor_fmt': _fmt_moeda(valor),
            'ticket_fmt': _fmt_moeda(ticket),
            'pct_faturamento_fmt': _fmt_percentual_1(valor, total_valor),
            'pct_exames_fmt': _fmt_percentual_1(qtd, total_qtd) if total_qtd else '0,0%',
        })
        chart_labels.append(rotulo)
        chart_faturamento.append(float(valor))
        chart_ticket.append(float(ticket))
        chart_cores.append(cor)

    mes_titulo = f'{MESES_PT[mes].upper()} {ano}'
    return {
        'titulo_relatorio': f'FATURAMENTO POR MODALIDADE — {mes_titulo}',
        'subtitulo_filtro': LEGENDA_FILTRO_ANALISES,
        'linhas_modalidade': linhas,
        'total_quantidade_fmt': _fmt_numero_int(total_qtd),
        'total_valor_fmt': _fmt_moeda(total_valor),
        'total_ticket_fmt': _fmt_moeda(ticket_geral),
        'total_pct_faturamento_fmt': '100,0%' if linhas else '—',
        'total_pct_exames_fmt': '100,0%' if linhas else '—',
        'chart_modalidade_labels_json': json.dumps(chart_labels, ensure_ascii=False),
        'chart_faturamento_data_json': json.dumps(chart_faturamento),
        'chart_ticket_data_json': json.dumps(chart_ticket),
        'chart_cores_json': json.dumps(chart_cores),
    }
