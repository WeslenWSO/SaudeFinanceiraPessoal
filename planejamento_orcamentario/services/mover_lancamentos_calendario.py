"""Move lançamentos do planejamento para outro dia (calendário)."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from planejamento_orcamentario.models import ItemOrcamento, LancamentoOrcamento
from planejamento_orcamentario.services.feriados_br import dia_nao_util, dia_util
from planejamento_orcamentario.services.montar_calendario_despesas import TIPOS_DESPESA


class MoverLancamentoError(ValueError):
    pass


def mover_despesas_dia(
    empresa,
    data_origem: date,
    data_destino: date,
) -> dict:
    if data_origem == data_destino:
        raise MoverLancamentoError('Origem e destino são iguais.')

    if data_origem.year != data_destino.year or data_origem.month != data_destino.month:
        raise MoverLancamentoError('Origem e destino devem estar no mesmo mês.')

    if not dia_nao_util(data_origem):
        raise MoverLancamentoError(
            'Só é possível arrastar despesas que caem em sábado, domingo ou feriado.'
        )

    if not dia_util(data_destino):
        raise MoverLancamentoError(
            'Solte em um dia útil (segunda a sexta, exceto feriado nacional).'
        )

    qs = LancamentoOrcamento.objects.filter(
        empresa=empresa,
        data_lancamento=data_origem,
        item__ativo=True,
        item__tipo__in=TIPOS_DESPESA,
    ).select_related('item')

    if not qs.exists():
        raise MoverLancamentoError('Nenhuma despesa encontrada na data de origem.')

    item_ids = list(qs.values_list('item_id', flat=True).distinct())

    with transaction.atomic():
        qtd = qs.update(data_lancamento=data_destino)
        itens_atualizados = 0
        for item in ItemOrcamento.objects.filter(pk__in=item_ids):
            if not item.data_inicio or item.data_inicio.day != data_origem.day:
                continue
            try:
                novo_inicio = item.data_inicio.replace(day=data_destino.day)
            except ValueError:
                from calendar import monthrange

                ultimo = monthrange(item.data_inicio.year, item.data_inicio.month)[1]
                novo_inicio = item.data_inicio.replace(day=min(data_destino.day, ultimo))
            if novo_inicio != item.data_inicio:
                item.data_inicio = novo_inicio
                item.save(update_fields=['data_inicio', 'atualizado_em'])
                itens_atualizados += 1

    return {
        'lancamentos_movidos': qtd,
        'itens_atualizados': itens_atualizados,
        'data_origem': data_origem.isoformat(),
        'data_destino': data_destino.isoformat(),
    }
