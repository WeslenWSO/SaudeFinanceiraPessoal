"""Relatório mensal de faturamento por convênio/parceiro (aba Análises)."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Q

from faturamento_medico.dashboard_exames import MESES_PT, STATUS_AGENDAMENTO_CANCELADOS
from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.ranking_exames import montar_ranking_exames_qs

from dashboard.analises_agendamento import (
    ROTULO_PENDENCIA_PACS,
    agendamento_conta_faturamento_convenio,
    agendamento_pendencia_pacs_convenio,
)
from dashboard.analises_conferencia import kwargs_ranking_faturamento_analise
from faturamento_medico.services.valor_pago_exibicao import valor_agregacao_analises


def _q_cancelados():
    q = Q()
    for status in STATUS_AGENDAMENTO_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _fmt_moeda(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return '0,00'
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s


def _fmt_moeda_inteiro(valor) -> str:
    """Ex.: 706.198,53 no print."""
    return _fmt_moeda(valor)


def _fmt_numero_int(valor: int) -> str:
    return f'{valor:,}'.replace(',', '.')


def _fmt_percentual(parte: Decimal, total: Decimal) -> str:
    if not total:
        return '0,00%'
    pct = (parte / total) * Decimal('100')
    return f'{pct:.2f}'.replace('.', ',') + '%'


def _contar_dias_trabalhados_convenio_agendamento(qs) -> int:
    dias: set = set()
    for fat in qs.prefetch_related('itens_servico'):
        if not agendamento_conta_faturamento_convenio(fat):
            continue
        if fat.data:
            dias.add(fat.data)
    return len(dias)


def _montar_pendencias_pacs_por_convenio(qs) -> list[dict]:
    por_conv: dict[str, dict] = {}
    for fat in qs.prefetch_related('itens_servico'):
        if not agendamento_pendencia_pacs_convenio(fat):
            continue
        conv = _rotulo_convenio_exibicao(fat.convenio)
        if conv not in por_conv:
            por_conv[conv] = {'quantidade': 0, 'valor': Decimal('0')}
        itens = list(fat.itens_servico.all())
        if not itens:
            por_conv[conv]['quantidade'] += 1
            por_conv[conv]['valor'] += valor_agregacao_analises(None, fat)
            continue
        for item in itens:
            por_conv[conv]['quantidade'] += 1
            por_conv[conv]['valor'] += valor_agregacao_analises(item, fat)
    linhas = []
    for conv, d in sorted(por_conv.items(), key=lambda x: (-x[1]['valor'], x[0])):
        linhas.append({
            'convenio': conv,
            'quantidade': d['quantidade'],
            'quantidade_fmt': _fmt_numero_int(d['quantidade']),
            'valor_fmt': _fmt_moeda_inteiro(d['valor']),
        })
    return linhas


def kwargs_ranking_convenio_analise(empresa_id: int) -> dict:
    base = kwargs_ranking_faturamento_analise(empresa_id)
    return {
        **base,
        'somente_status_analise': False,
        'somente_agendamento_faturamento_convenio': True,
    }


def _rotulo_convenio_exibicao(nome: str) -> str:
    n = (nome or '').strip()
    if not n:
        return 'PARTICULAR'
    if n.lower() in ('particular', 'part'):
        return 'PARTICULAR'
    return n.upper()


def montar_relatorio_faturamento_convenio(empresa_id: int, ano: int, mes: int) -> dict:
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

    dias_trabalhados = _contar_dias_trabalhados_convenio_agendamento(qs)

    ranking = montar_ranking_exames_qs(qs, **kwargs_ranking_convenio_analise(empresa_id))
    pendencias_pacs = _montar_pendencias_pacs_por_convenio(qs)
    total_qtd = ranking['total_quantidade']
    total_valor = ranking['total_valor']

    ticket_medio = (total_valor / total_qtd) if total_qtd else Decimal('0')
    media_dia = (total_valor / dias_trabalhados) if dias_trabalhados else Decimal('0')

    linhas = []
    for row in ranking['ranking_convenios']:
        valor = row['valor']
        linhas.append({
            'convenio': _rotulo_convenio_exibicao(row['convenio']),
            'quantidade': row['quantidade'],
            'quantidade_fmt': _fmt_numero_int(row['quantidade']),
            'valor': valor,
            'valor_fmt': _fmt_moeda_inteiro(valor),
            'percentual_fmt': _fmt_percentual(valor, total_valor),
        })

    mes_titulo = f'{MESES_PT[mes].upper()} {ano}'
    return {
        'titulo_relatorio': f'RELATÓRIO DE FATURAMENTO — {mes_titulo}',
        'subtitulo_periodo': (
            f'{dias_trabalhados} dias trabalhados | '
            f'Período: {inicio.strftime("%d/%m/%Y")} a {fim.strftime("%d/%m/%Y")} | '
            f'Faturamento: status agendamento Aguardando faturamento e Concluído (RIS)'
        ),
        'pendencias_pacs_convenio': pendencias_pacs,
        'rotulo_pendencia_pacs': ROTULO_PENDENCIA_PACS,
        'kpi_faturamento_total_fmt': _fmt_moeda_inteiro(total_valor),
        'kpi_atendimentos_fmt': _fmt_numero_int(total_qtd),
        'kpi_ticket_medio_fmt': _fmt_moeda_inteiro(ticket_medio),
        'kpi_media_dia_fmt': _fmt_moeda_inteiro(media_dia),
        'linhas_convenio': linhas,
        'total_quantidade': total_qtd,
        'total_quantidade_fmt': _fmt_numero_int(total_qtd),
        'total_valor_fmt': _fmt_moeda_inteiro(total_valor),
        'total_percentual_fmt': '100%',
        'data_inicio': inicio.isoformat(),
        'data_fim': fim.isoformat(),
    }
