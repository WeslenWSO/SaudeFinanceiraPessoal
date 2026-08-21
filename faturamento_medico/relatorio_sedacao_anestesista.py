"""Relatório de sedação — lançamentos de anestesista por período."""

from __future__ import annotations

from decimal import Decimal

from .models import LancamentoAnestesistaExame


def _procedimento_lancamento(lan, fat) -> str:
    """Procedimento do exame (item vinculado ou itens do faturamento)."""
    item = lan.item_servico
    if item is not None:
        proc = (item.servico or '').strip()
        if proc:
            return proc
    procs = [
        (it.servico or '').strip()
        for it in fat.itens_servico.all()
        if (it.servico or '').strip()
    ]
    if procs:
        return ', '.join(dict.fromkeys(procs))
    return (fat.servico or '').strip() or '-'


def montar_relatorio_sedacao_anestesista(empresa_id, data_inicio, data_fim, *, anestesista=''):
    """Lista linhas do relatório filtradas pela data do faturamento."""
    qs = (
        LancamentoAnestesistaExame.objects
        .filter(
            faturamento__empresa_id=empresa_id,
            faturamento__data__gte=data_inicio,
            faturamento__data__lte=data_fim,
        )
        .select_related('faturamento', 'item_servico')
        .prefetch_related('faturamento__itens_servico')
        .order_by('faturamento__data', 'faturamento__nome', 'id')
    )
    anest = (anestesista or '').strip()
    if anest:
        qs = qs.filter(medico__icontains=anest)

    linhas = []
    total = Decimal('0')
    for lan in qs:
        fat = lan.faturamento
        linhas.append({
            'id': lan.id,
            'pago': lan.pago,
            'data': fat.data,
            'data_fmt': fat.data.strftime('%d/%m/%Y') if fat.data else '-',
            'paciente': (fat.nome or '').strip() or '-',
            'procedimento': _procedimento_lancamento(lan, fat),
            'exame': (lan.exame or '').strip() or '-',
            'medico_anestesista': (lan.medico or '').strip() or '-',
            'valor_sedacao': lan.valor or Decimal('0'),
            'medico': (fat.medico or '').strip() or '-',
        })
        total += lan.valor or Decimal('0')

    return {
        'linhas': linhas,
        'total_valor': total,
        'quantidade': len(linhas),
    }
