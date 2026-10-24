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
        'faturamento_convenio',
        'Por convênio',
        'Faturamento por convênio ou parceiros — relatório mensal.',
        'fa-file-invoice-dollar',
        'dashboard/partials/analise_modelo_faturamento_convenio.html',
    ),
    AnaliseModeloDef(
        'faturamento_modalidade',
        'Por modalidade',
        'Faturamento por modalidade — tabela, pizza e ticket médio.',
        'fa-x-ray',
        'dashboard/partials/analise_modelo_faturamento_modalidade.html',
    ),
    AnaliseModeloDef(
        'detalhes_modalidade_convenio',
        'Modalidade × convênio',
        'Detalhes por modalidade e convênio — tabela e TOP 5/10.',
        'fa-th-list',
        'dashboard/partials/analise_modelo_detalhes_modalidade_convenio.html',
    ),
    AnaliseModeloDef(
        'exames_convenio',
        'Exames por convênio e conferência',
        'Tabelas por convênio: status, quantidade, clientes e valor no mês.',
        'fa-layer-group',
        'dashboard/partials/analise_modelo_exames_convenio.html',
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
