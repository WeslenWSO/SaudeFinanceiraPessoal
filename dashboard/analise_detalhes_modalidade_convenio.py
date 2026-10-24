"""Detalhes por modalidade e convênio (tabela + TOP N por modalidade)."""
from __future__ import annotations

import json
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from faturamento_medico.dashboard_exames import MESES_PT
from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.ranking_exames import _label_convenio, _valor_item

from dashboard.analise_faturamento_convenio import (
    _fmt_moeda,
    _fmt_numero_int,
    _q_cancelados,
)
from dashboard.analise_faturamento_modalidade import (
    CORES_MODALIDADE,
    ROTULOS_MODALIDADE,
    _codigo_modalidade,
    _fmt_percentual_1,
)

TITULOS_BANNER = {
    'MR': 'RESSONÂNCIA MAGNÉTICA',
    'CT': 'TOMOGRAFIA',
    'US': 'ULTRASSONOGRAFIA',
    'MG': 'MAMOGRAFIA',
    'CR': 'RAIO-X',
    'EC': 'ELETROCARDIOGRAMA',
    'EG': 'ELETROENCEFALOGRAMA',
    'OUTROS': 'OUTROS',
}

TITULOS_TOTAL = {
    'MR': 'Total Ressonância',
    'CT': 'Total Tomografia',
    'US': 'Total Ultrassonografia',
    'MG': 'Total Mamografia',
    'CR': 'Total Raio-X',
    'EC': 'Total Eletrocardiograma',
    'EG': 'Total Eletroencefalograma',
    'OUTROS': 'Total Outros',
}

ORDEM_MODALIDADES = ('MR', 'CT', 'US', 'MG', 'CR', 'EC', 'EG', 'OUTROS')

TOP_N_PADRAO = 5
TOP_N_GRANDE = 10
MODALIDADES_TOP_10 = frozenset({'MR', 'US'})


def _convenio_exibicao(nome: str | None) -> str:
    return _label_convenio(nome).upper()


def _cores_grafico(base: str, n: int) -> list[str]:
    """Duas tonalidades alternadas para barras horizontais."""
    if n <= 0:
        return []
    escuro = base
    claro = base
    if base == '#4472C4':
        claro = '#8FAADC'
    elif base == '#70AD47':
        claro = '#A9D18E'
    elif base == '#9DC3E6':
        claro = '#BDD7EE'
    elif base == '#FFC000':
        claro = '#FFE699'
    elif base == '#C55A11':
        claro = '#E2A173'
    else:
        claro = '#adb5bd'
    return [escuro if i % 2 == 0 else claro for i in range(n)]


def montar_detalhes_modalidade_convenio(empresa_id: int, ano: int, mes: int) -> dict:
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

    por_mod_conv: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')}),
    )

    for fat in qs:
        itens = list(fat.itens_servico.all())
        conv = _convenio_exibicao(fat.convenio)
        if not itens:
            cod = _codigo_modalidade(fat, None)
            por_mod_conv[cod][conv]['quantidade'] += 1
            por_mod_conv[cod][conv]['valor'] += _valor_item(None, fat)
            continue
        for item in itens:
            cod = _codigo_modalidade(fat, item)
            por_mod_conv[cod][conv]['quantidade'] += 1
            por_mod_conv[cod][conv]['valor'] += _valor_item(item, fat)

    secoes = []
    for codigo in ORDEM_MODALIDADES:
        bloco_conv = por_mod_conv.get(codigo)
        if not bloco_conv:
            continue

        linhas_raw = sorted(
            bloco_conv.items(),
            key=lambda x: (-float(x[1]['valor']), -x[1]['quantidade'], x[0]),
        )
        total_qtd = sum(d['quantidade'] for _, d in linhas_raw)
        total_valor = sum((d['valor'] for _, d in linhas_raw), Decimal('0'))
        if total_qtd == 0:
            continue

        ticket_total = (total_valor / total_qtd) if total_qtd else Decimal('0')
        cor = CORES_MODALIDADE.get(codigo, '#6c757d')

        linhas = []
        for convenio, dados in linhas_raw:
            qtd = dados['quantidade']
            valor = dados['valor']
            ticket = (valor / qtd) if qtd else Decimal('0')
            linhas.append({
                'convenio': convenio,
                'quantidade_fmt': _fmt_numero_int(qtd),
                'valor_fmt': _fmt_moeda(valor),
                'ticket_fmt': _fmt_moeda(ticket),
                'pct_modal_fmt': _fmt_percentual_1(valor, total_valor),
            })

        top_n = TOP_N_GRANDE if codigo in MODALIDADES_TOP_10 else TOP_N_PADRAO
        top_linhas = linhas_raw[:top_n]
        chart_labels = [c for c, _ in reversed(top_linhas)]
        chart_data = [float(d['valor']) for _, d in reversed(top_linhas)]
        chart_cores = _cores_grafico(cor, len(chart_labels))

        secoes.append({
            'codigo': codigo,
            'titulo': TITULOS_BANNER.get(codigo, codigo),
            'titulo_total': TITULOS_TOTAL.get(codigo, 'Total'),
            'cor_header': cor,
            'cor_footer': cor,
            'top_n': top_n,
            'linhas': linhas,
            'total_quantidade_fmt': _fmt_numero_int(total_qtd),
            'total_valor_fmt': _fmt_moeda(total_valor),
            'total_ticket_fmt': _fmt_moeda(ticket_total),
            'total_pct_fmt': '100,0%',
            'chart_titulo': f"{TITULOS_BANNER.get(codigo, codigo)} (TOP {top_n})",
            'chart_labels_json': json.dumps(chart_labels, ensure_ascii=False),
            'chart_data_json': json.dumps(chart_data),
            'chart_cores_json': json.dumps(chart_cores),
        })

    mes_titulo = f'{MESES_PT[mes].upper()} {ano}'
    charts_boot = [
        {
            'canvas_id': f'chartModDet{c["codigo"]}',
            'labels': json.loads(c['chart_labels_json']),
            'data': json.loads(c['chart_data_json']),
            'cores': json.loads(c['chart_cores_json']),
        }
        for c in secoes
    ]

    return {
        'titulo_relatorio': f'DETALHES POR MODALIDADE E CONVÊNIO — {mes_titulo}',
        'secoes_modalidade': secoes,
        'charts_detalhes_json': json.dumps(charts_boot, ensure_ascii=False),
    }
