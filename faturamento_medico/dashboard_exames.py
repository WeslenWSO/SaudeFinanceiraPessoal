"""Agregação para o dashboard de exames por convênio e status de conferência."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.urls import reverse
from urllib.parse import urlencode

from .lote_utils import faturamento_tem_lote_interno, ids_lotes_internos
from .models import FaturamentoMedico, ItemServico

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


def _q_cancelados():
    q = Q()
    for status in STATUS_AGENDAMENTO_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _status_linha(faturamento, item=None, ids_internos=None):
    tem_lote = faturamento_tem_lote_interno(faturamento, ids_internos=ids_internos)
    if item is not None:
        status_label, status_css = item.status_conferencia_badge()
        if tem_lote and (status_label in ('CONFERIDO', 'LOTE OK') or item.conferido):
            return 'LOTE OK', ItemServico.STATUS_CONFERENCIA_CSS['LOTE OK']
        return status_label, status_css
    if not (faturamento.guia or '').strip():
        return 'FALTA DE GUIA', ItemServico.STATUS_CONFERENCIA_CSS.get('FALTA DE GUIA', 'warning')
    if not faturamento.total:
        return 'FALTA DE VALOR NA TABELA', ItemServico.STATUS_CONFERENCIA_CSS.get(
            'FALTA DE VALOR NA TABELA', 'danger'
        )
    return 'PENDENTE', ItemServico.STATUS_CONFERENCIA_CSS['PENDENTE']


def _link_listagem(data_inicio, data_fim, convenio='', status=''):
    params = [
        ('data_inicio', data_inicio),
        ('data_fim', data_fim),
    ]
    if status:
        params.append(('status_conferencia', status))
    if convenio and convenio != 'Não informado':
        params.append(('convenio', convenio))
    return f"{reverse('faturamento_medico:ftlistar')}?{urlencode(params)}"


def _acumular(stats, totais_gerais, convenio, status_label, valor):
    stats[convenio][status_label]['quantidade'] += 1
    stats[convenio][status_label]['valor'] += valor
    totais_gerais[status_label]['quantidade'] += 1
    totais_gerais[status_label]['valor'] += valor


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
    ids_internos = ids_lotes_internos(empresa_id)

    stats = defaultdict(lambda: defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')}))
    totais_gerais = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})

    for fat in qs:
        conv = (fat.convenio or '').strip() or 'Não informado'
        itens = list(fat.itens_servico.all())
        if not itens:
            status_label, _ = _status_linha(fat, ids_internos=ids_internos)
            valor = Decimal(str(fat.total or 0))
            _acumular(stats, totais_gerais, conv, status_label, valor)
            continue
        for item in itens:
            status_label, _ = _status_linha(fat, item, ids_internos=ids_internos)
            valor = item.total if item.total is not None else (item.valor or Decimal('0'))
            if not isinstance(valor, Decimal):
                valor = Decimal(str(valor))
            _acumular(stats, totais_gerais, conv, status_label, valor)

    ordem_status = [c[0] for c in ItemServico.STATUS_CONFERENCIA_CHOICES]

    def _montar_linhas(bloco, convenio=None):
        linhas = []
        total_q = 0
        total_v = Decimal('0')
        for st in ordem_status:
            d = bloco.get(st)
            if not d or d['quantidade'] == 0:
                continue
            linhas.append({
                'status': st,
                'css': ItemServico.STATUS_CONFERENCIA_CSS.get(st, 'secondary'),
                'quantidade': d['quantidade'],
                'valor': d['valor'],
                'url_listagem': _link_listagem(data_inicio, data_fim, convenio, st),
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
