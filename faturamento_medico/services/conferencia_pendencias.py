"""Pendências de conferência e de agendamento (RIS) — tela Conferência."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.urls import reverse
from urllib.parse import urlencode

from dashboard.analise_faturamento_convenio import _fmt_moeda, _fmt_numero_int, _q_cancelados
from dashboard.analise_validacao_conferencia import montar_relatorio_validacao_conferencia
from dashboard.analises_agendamento import (
    ROTULO_PENDENCIA_PACS,
    STATUS_AGENDAMENTO_CONFIRMADO_RIS,
    agendamento_pendencia_pacs_convenio,
    rotulo_exibicao_agendamento_dashboard,
)
from faturamento_medico.dashboard_exames import MESES_PT
from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.ranking_exames import _valor_item
from faturamento_medico.services.valor_pago_exibicao import valor_agregacao_analises


def _link_listagem(data_inicio: str, data_fim: str, *, status_conferencia='', status_agendamento='', convenio=''):
    params = [('data_inicio', data_inicio), ('data_fim', data_fim)]
    if status_agendamento:
        params.append(('status_agendamento', status_agendamento))
    elif status_conferencia:
        params.append(('status_conferencia', status_conferencia))
    if convenio and convenio != 'Não informado':
        params.append(('convenio', convenio))
    return f"{reverse('faturamento_medico:ftlistar')}?{urlencode(params)}"


def _montar_linhas_agendamento_confirmado(empresa_id: int, inicio: date, fim: date) -> list[dict]:
    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=inicio,
            data__lte=fim,
        )
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )
    por_conv: dict[str, dict] = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})
    total_q = 0
    total_v = Decimal('0')
    data_ini = inicio.isoformat()
    data_fim = fim.isoformat()

    for fat in qs:
        if not agendamento_pendencia_pacs_convenio(fat):
            continue
        conv = (fat.convenio or '').strip() or 'Não informado'
        itens = list(fat.itens_servico.all())
        if not itens:
            val = valor_agregacao_analises(None, fat)
            por_conv[conv]['quantidade'] += 1
            por_conv[conv]['valor'] += val
            total_q += 1
            total_v += val
            continue
        for item in itens:
            val = _valor_item(item, fat)
            por_conv[conv]['quantidade'] += 1
            por_conv[conv]['valor'] += val
            total_q += 1
            total_v += val

    linhas = []
    for conv, d in sorted(por_conv.items(), key=lambda x: (-float(x[1]['valor']), x[0].lower())):
        linhas.append({
            'convenio': conv,
            'rotulo': ROTULO_PENDENCIA_PACS,
            'status_agendamento': STATUS_AGENDAMENTO_CONFIRMADO_RIS,
            'quantidade_fmt': _fmt_numero_int(d['quantidade']),
            'valor_fmt': _fmt_moeda(d['valor']),
            'url_listagem': _link_listagem(
                data_ini,
                data_fim,
                status_agendamento=STATUS_AGENDAMENTO_CONFIRMADO_RIS,
                convenio=conv,
            ),
        })

    return linhas, total_q, total_v


def montar_conferencia_pendencias(empresa_id: int, ano: int, mes: int) -> dict:
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    data_ini = inicio.isoformat()
    data_fim = fim.isoformat()
    mes_titulo = f'{MESES_PT[mes].upper()} {ano}'

    validacao = montar_relatorio_validacao_conferencia(empresa_id, ano, mes)
    linhas_conferencia = []
    for linha in validacao.get('linhas_status') or []:
        if linha.get('incluido_analise'):
            continue
        status = linha.get('status') or ''
        linhas_conferencia.append({
            **linha,
            'tipo': 'conferencia',
            'url_listagem': _link_listagem(data_ini, data_fim, status_conferencia=status),
        })
    qtd_conf = sum(int(l.get('quantidade') or 0) for l in linhas_conferencia)
    val_conf = sum((l.get('valor') or Decimal('0') for l in linhas_conferencia), Decimal('0'))

    linhas_ag, qtd_ag, val_ag = _montar_linhas_agendamento_confirmado(empresa_id, inicio, fim)

    total_pend_q = qtd_conf + qtd_ag
    total_pend_v = val_conf + val_ag

    return {
        'titulo': f'Conferência — pendências — {mes_titulo}',
        'periodo_fmt': f'{inicio.strftime("%d/%m/%Y")} a {fim.strftime("%d/%m/%Y")}',
        'mes_filtro': f'{ano:04d}-{mes:02d}',
        'linhas_conferencia': linhas_conferencia,
        'linhas_agendamento_confirmado': linhas_ag,
        'rotulo_pendencia_pacs': ROTULO_PENDENCIA_PACS,
        'rotulo_agendamento_confirmado': rotulo_exibicao_agendamento_dashboard(
            STATUS_AGENDAMENTO_CONFIRMADO_RIS
        ),
        'total_conferencia_quantidade_fmt': validacao.get('excluidos_quantidade_fmt', '0'),
        'total_conferencia_valor_fmt': validacao.get('excluidos_valor_fmt', '0,00'),
        'total_agendamento_quantidade_fmt': _fmt_numero_int(qtd_ag),
        'total_agendamento_valor_fmt': _fmt_moeda(val_ag),
        'total_pendencias_quantidade_fmt': _fmt_numero_int(total_pend_q),
        'total_pendencias_valor_fmt': _fmt_moeda(total_pend_v),
        'url_listagem_confirmado_mes': _link_listagem(
            data_ini,
            data_fim,
            status_agendamento=STATUS_AGENDAMENTO_CONFIRMADO_RIS,
        ),
    }
