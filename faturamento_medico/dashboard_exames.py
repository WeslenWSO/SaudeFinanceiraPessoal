"""Agregação para o dashboard de exames por convênio e status de faturamento."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.urls import reverse
from urllib.parse import urlencode

from .models import FaturamentoMedico

STATUS_AGENDAMENTO_CANCELADOS = (
    'Cancelado',
    'Desistência',
    'Desistencia',
    'Deletado',
    'Deleção',
    'Delecao',
)

MESES_PT = (
    '',
    'Janeiro',
    'Fevereiro',
    'Março',
    'Abril',
    'Maio',
    'Junho',
    'Julho',
    'Agosto',
    'Setembro',
    'Outubro',
    'Novembro',
    'Dezembro',
)

STATUS_DASHBOARD = FaturamentoMedico.FATURAMENTO_STATUS_CHOICES

STATUS_DASHBOARD_CSS = {
    'pendente': 'secondary',
    'aguardando_pagamento': 'warning',
    'enviado': 'info',
    'finalizado': 'success',
}

STATUS_DASHBOARD_LABEL = dict(STATUS_DASHBOARD)
STATUS_DASHBOARD_KEYS = {k for k, _ in STATUS_DASHBOARD}


def _q_cancelados():
    q = Q()
    for status in STATUS_AGENDAMENTO_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _status_faturamento(faturamento):
    key = (faturamento.status or 'pendente').strip() or 'pendente'
    if key not in STATUS_DASHBOARD_KEYS:
        key = 'pendente'
    return key, STATUS_DASHBOARD_LABEL[key]


def _link_listagem(data_inicio, data_fim, convenio='', status_key=''):
    params = [
        ('data_inicio', data_inicio),
        ('data_fim', data_fim),
    ]
    if status_key:
        params.append(('status', status_key))
    if convenio and convenio != 'Não informado':
        params.append(('convenio', convenio))
    return f"{reverse('faturamento_medico:ftlistar')}?{urlencode(params)}"


def _acumular(stats, totais_gerais, convenio, status_key, valor):
    stats[convenio][status_key]['quantidade'] += 1
    stats[convenio][status_key]['valor'] += valor
    totais_gerais[status_key]['quantidade'] += 1
    totais_gerais[status_key]['valor'] += valor


def _q_convenio_filtro(nome: str) -> Q:
    conv = (nome or '').strip()
    if not conv:
        return Q()
    return Q(convenio__iexact=conv)


def montar_dashboard_exames(empresa_id, ano, mes, convenios=None):
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    data_inicio = inicio.isoformat()
    data_fim = fim.isoformat()
    convenios_sel = [c.strip() for c in (convenios or []) if c and str(c).strip()]

    qs = (
        FaturamentoMedico.objects
        .filter(empresa_id=empresa_id, data__gte=inicio, data__lte=fim)
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )
    if convenios_sel:
        q_conv = Q()
        for conv in convenios_sel:
            q_conv |= _q_convenio_filtro(conv)
        qs = qs.filter(q_conv)

    stats = defaultdict(lambda: defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')}))
    totais_gerais = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})

    for fat in qs:
        conv = (fat.convenio or '').strip() or 'Não informado'
        status_key, _ = _status_faturamento(fat)
        itens = list(fat.itens_servico.all())
        if not itens:
            valor = Decimal(str(fat.total or 0))
            _acumular(stats, totais_gerais, conv, status_key, valor)
            continue
        for item in itens:
            valor = item.total if item.total is not None else (item.valor or Decimal('0'))
            if not isinstance(valor, Decimal):
                valor = Decimal(str(valor))
            _acumular(stats, totais_gerais, conv, status_key, valor)

    ordem_status = [k for k, _ in STATUS_DASHBOARD]

    def _montar_linhas(bloco, convenio=None):
        linhas = []
        total_q = 0
        total_v = Decimal('0')
        for st_key in ordem_status:
            d = bloco.get(st_key)
            if not d or d['quantidade'] == 0:
                continue
            linhas.append({
                'status': STATUS_DASHBOARD_LABEL[st_key],
                'status_key': st_key,
                'css': STATUS_DASHBOARD_CSS.get(st_key, 'secondary'),
                'quantidade': d['quantidade'],
                'valor': d['valor'],
                'url_listagem': _link_listagem(data_inicio, data_fim, convenio, st_key),
            })
            total_q += d['quantidade']
            total_v += d['valor']
        return linhas, total_q, total_v

    cards = []
    for conv in sorted(stats.keys(), key=lambda x: x.lower()):
        linhas, total_q, total_v = _montar_linhas(stats[conv], convenio=conv)
        cards.append({
            'convenio': conv,
            'status_linhas': linhas,
            'total_quantidade': total_q,
            'total_valor': total_v,
            'url_listagem': _link_listagem(data_inicio, data_fim, conv, ''),
        })

    geral_linhas, geral_q, geral_v = _montar_linhas(totais_gerais)

    return {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'mes_label': f'{MESES_PT[mes]} / {ano}',
        'convenios_selecionados': convenios_sel,
        'cards': cards,
        'totais_gerais': {
            'status_linhas': geral_linhas,
            'total_quantidade': geral_q,
            'total_valor': geral_v,
        },
    }
