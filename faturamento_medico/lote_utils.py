"""Utilitários para distinguir lote interno (modelo Lote) do lote do convênio (GEAP etc.)."""
from __future__ import annotations

from .models import FaturamentoMedico, Lote


def ids_lotes_internos(empresa_id: int) -> set[str]:
    return {str(pk) for pk in Lote.objects.filter(empresa_id=empresa_id).values_list('id', flat=True)}


def faturamento_tem_lote_interno(
    faturamento: FaturamentoMedico,
    *,
    ids_internos: set[str] | None = None,
) -> bool:
    lote = (faturamento.lote or '').strip()
    if not lote:
        return False
    if ids_internos is None:
        ids_internos = ids_lotes_internos(faturamento.empresa_id)
    return lote in ids_internos


def faturamento_elegivel_lote(faturamento: FaturamentoMedico, *, ids_internos: set[str] | None = None) -> bool:
    """Pendente, sem lote interno, com itens conferidos."""
    if (faturamento.status or '').strip() != 'pendente':
        return False
    if faturamento_tem_lote_interno(faturamento, ids_internos=ids_internos):
        return False
    return faturamento.itens_servico.filter(conferido=True).exists()
