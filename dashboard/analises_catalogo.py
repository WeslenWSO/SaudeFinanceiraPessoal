"""Catálogo de relatórios da aba Análises (layout mensal; títulos alinháveis ao PDF de referência)."""
from __future__ import annotations

from dataclasses import dataclass

# Abas no /dash/ — False oculta o link (acesso direto: ?aba=financeiro ou ?aba=analises)
ABA_FINANCEIRO_DASHBOARD_VISIVEL = False
ABA_ANALISES_DASHBOARD_VISIVEL = True


@dataclass(frozen=True)
class AnaliseModeloDef:
    codigo: str
    titulo: str
    descricao: str
    icon: str = 'fa-chart-bar'
    template_partial: str = ''
    exibir_aba: bool = True


MODELOS_ANALISE: tuple[AnaliseModeloDef, ...] = (
    AnaliseModeloDef(
        'validacao_conferencia',
        'Validação conferência',
        'Status de conferência — o que entra ou não no faturamento das análises.',
        'fa-clipboard-check',
        'dashboard/partials/analise_modelo_validacao_conferencia.html',
        exibir_aba=False,
    ),
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
        'evolucao_faturamento',
        'Evolução',
        'Evolução histórica do faturamento — escolha até 12 meses.',
        'fa-chart-line',
        'dashboard/partials/analise_modelo_evolucao_faturamento.html',
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


def modelos_analise_aba() -> tuple[AnaliseModeloDef, ...]:
    return tuple(m for m in MODELOS_ANALISE if m.exibir_aba)


def modelo_analise_padrao() -> AnaliseModeloDef:
    visiveis = modelos_analise_aba()
    return visiveis[0] if visiveis else MODELOS_ANALISE[0]
