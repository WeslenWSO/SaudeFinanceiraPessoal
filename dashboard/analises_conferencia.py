"""Regras de status de conferência para relatórios da aba Análises."""
from __future__ import annotations

from faturamento_medico.dashboard_exames import _status_linha
from faturamento_medico.lote_utils import ids_lotes_internos

# Incluídos no faturamento das Análises (demais status ficam só no relatório de validação).
STATUS_CONFERENCIA_INCLUIDOS_ANALISE: frozenset[str] = frozenset({
    'CONFERIDO',  # Aguardando o faturamento
    'LOTE OK',  # Concluído
})

ROTULOS_STATUS_ANALISE: dict[str, str] = {
    'CONFERIDO': 'Aguardando o faturamento',
    'LOTE OK': 'Concluído',
}


def rotulo_status_analise(status: str) -> str:
    s = (status or '').strip() or 'PENDENTE'
    return ROTULOS_STATUS_ANALISE.get(s, s)


def item_conta_faturamento_analise(faturamento, item, *, ids_internos=None) -> bool:
    label, _ = _status_linha(faturamento, item, ids_internos=ids_internos)
    return label in STATUS_CONFERENCIA_INCLUIDOS_ANALISE


def ids_lotes_empresa(empresa_id: int) -> set:
    return ids_lotes_internos(empresa_id)


def kwargs_ranking_faturamento_analise(empresa_id: int) -> dict:
    return {
        'somente_status_analise': True,
        'ids_lotes_internos': ids_lotes_empresa(empresa_id),
    }


def contar_dias_trabalhados_analise(qs, empresa_id: int) -> int:
    ids_internos = ids_lotes_empresa(empresa_id)
    dias: set = set()
    for fat in qs.prefetch_related('itens_servico'):
        itens = list(fat.itens_servico.all())
        if not itens:
            if item_conta_faturamento_analise(fat, None, ids_internos=ids_internos):
                dias.add(fat.data)
            continue
        for item in itens:
            if item_conta_faturamento_analise(fat, item, ids_internos=ids_internos):
                dias.add(fat.data)
                break
    return len(dias)
