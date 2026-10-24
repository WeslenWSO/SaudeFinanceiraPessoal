"""Catálogo de relatórios da aba Análises (layout mensal; títulos alinháveis ao PDF de referência)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnaliseModeloDef:
    codigo: str
    titulo: str
    descricao: str
    icon: str = 'fa-chart-bar'
    template_partial: str = ''


MODELOS_ANALISE: tuple[AnaliseModeloDef, ...] = (
    AnaliseModeloDef(
        'exames_convenio',
        'Exames por convênio e conferência',
        'Total geral e tabelas por convênio: status, quantidade, clientes e valor no mês.',
        'fa-layer-group',
        'dashboard/partials/analise_modelo_exames_convenio.html',
    ),
    AnaliseModeloDef(
        'producao_conferencia',
        'Produção diária — log de conferência',
        'Régua do mês e produção por usuário × convênio × status (data do log).',
        'fa-calendar-day',
        'dashboard/partials/analise_modelo_producao_conferencia.html',
    ),
)


def modelo_analise_ativo(codigo: str | None) -> AnaliseModeloDef | None:
    codigo = (codigo or '').strip().lower()
    if not codigo:
        return None
    for modelo in MODELOS_ANALISE:
        if modelo.codigo == codigo:
            return modelo
    return None


def modelo_analise_padrao() -> AnaliseModeloDef:
    return MODELOS_ANALISE[0]
