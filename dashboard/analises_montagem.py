"""Monta contexto dos relatórios mensais da aba Análises."""
from __future__ import annotations

from dashboard.analise_evolucao_faturamento import (
    montar_evolucao_faturamento,
    resolver_periodo_evolucao,
)
from dashboard.analise_faturamento_convenio import montar_relatorio_faturamento_convenio
from dashboard.analise_detalhes_modalidade_convenio import montar_detalhes_modalidade_convenio
from dashboard.analise_faturamento_modalidade import montar_relatorio_faturamento_modalidade
from dashboard.analise_validacao_conferencia import montar_relatorio_validacao_conferencia
from dashboard.analises_catalogo import (
    MODELOS_ANALISE,
    modelo_analise_ativo,
    modelo_analise_padrao,
)
from dashboard.analises_relatorio_apresentacao import urls_relatorio_analises
def montar_contexto_aba_analises(
    request,
    empresa_id: int,
    *,
    ano: int,
    mes: int,
    regime: str,
    modelo_codigo: str | None,
) -> dict:
    modelo = modelo_analise_ativo(modelo_codigo) or modelo_analise_padrao()
    mes_filtro = f'{ano:04d}-{mes:02d}'

    q_base = request.GET.copy()
    q_base['aba'] = 'analises'
    q_base['mes'] = mes_filtro
    if regime:
        q_base['regime'] = regime
    q_base.pop('modelo', None)
    url_analise_modelo_base = '?' + q_base.urlencode() + '&modelo='

    ev_de, ev_mes_de, ev_ate, ev_mes_ate, ev_aviso = resolver_periodo_evolucao(
        request, ano_ref=ano, mes_ref=mes
    )

    ctx: dict = {
        'modelos_analise': MODELOS_ANALISE,
        'modelo_analise': modelo.codigo,
        'modelo_analise_titulo': modelo.titulo,
        'modelo_analise_descricao': modelo.descricao,
        'modelo_analise_partial': modelo.template_partial,
        'url_analise_modelo_base': url_analise_modelo_base,
        'mes_filtro_analise': mes_filtro,
        'regime': regime,
        'dash_aba': 'analises',
        'ev_periodo_de_value': f'{ev_de:04d}-{ev_mes_de:02d}',
        'ev_periodo_ate_value': f'{ev_ate:04d}-{ev_mes_ate:02d}',
        **urls_relatorio_analises(request, mes_filtro),
    }

    if modelo.codigo == 'validacao_conferencia':
        ctx.update(montar_relatorio_validacao_conferencia(empresa_id, ano, mes))
    elif modelo.codigo == 'faturamento_convenio':
        ctx.update(montar_relatorio_faturamento_convenio(empresa_id, ano, mes))
    elif modelo.codigo == 'faturamento_modalidade':
        ctx.update(montar_relatorio_faturamento_modalidade(empresa_id, ano, mes))
    elif modelo.codigo == 'detalhes_modalidade_convenio':
        ctx.update(montar_detalhes_modalidade_convenio(empresa_id, ano, mes))
    elif modelo.codigo == 'evolucao_faturamento':
        ctx.update(
            montar_evolucao_faturamento(empresa_id, ev_de, ev_mes_de, ev_ate, ev_mes_ate)
        )
        ctx['ev_periodo_aviso'] = ev_aviso

    return ctx
