"""Relatório de apresentação — todas as análises de faturamento em um HTML."""
from __future__ import annotations

from urllib.parse import urlencode

from django.template.loader import render_to_string
from django.urls import reverse

from dashboard.analise_detalhes_modalidade_convenio import montar_detalhes_modalidade_convenio
from dashboard.analise_evolucao_faturamento import (
    montar_evolucao_faturamento,
    resolver_periodo_evolucao,
)
from dashboard.analise_faturamento_convenio import montar_relatorio_faturamento_convenio
from dashboard.analise_faturamento_modalidade import montar_relatorio_faturamento_modalidade
from dashboard.analise_validacao_conferencia import montar_relatorio_validacao_conferencia
from dashboard.analises_catalogo import MODELOS_ANALISE


def params_query_relatorio_analises(request, mes_filtro: str) -> str:
    params: dict[str, str] = {'mes': mes_filtro}
    regime = (request.GET.get('regime') or '').strip()
    if regime:
        params['regime'] = regime
    for chave in ('ev_de', 'ev_ate'):
        val = (request.GET.get(chave) or '').strip()
        if val:
            params[chave] = val
    return urlencode(params)


def urls_relatorio_analises(request, mes_filtro: str) -> dict[str, str]:
    q = params_query_relatorio_analises(request, mes_filtro)
    return {
        'url_analises_apresentacao': f"{reverse('dashboard:analises_relatorio')}?{q}",
        'url_analises_pdf': f"{reverse('dashboard:analises_relatorio_pdf')}?{q}",
        'url_analises_whatsapp': reverse('dashboard:analises_relatorio_whatsapp'),
    }


def _contexto_modelo(empresa_id: int, request, ano: int, mes: int, codigo: str) -> dict:
    if codigo == 'validacao_conferencia':
        return montar_relatorio_validacao_conferencia(empresa_id, ano, mes)
    if codigo == 'faturamento_convenio':
        return montar_relatorio_faturamento_convenio(empresa_id, ano, mes)
    if codigo == 'faturamento_modalidade':
        return montar_relatorio_faturamento_modalidade(empresa_id, ano, mes)
    if codigo == 'detalhes_modalidade_convenio':
        return montar_detalhes_modalidade_convenio(empresa_id, ano, mes)
    if codigo == 'evolucao_faturamento':
        ev_de, ev_mes_de, ev_ate, ev_mes_ate, ev_aviso = resolver_periodo_evolucao(
            request, ano_ref=ano, mes_ref=mes
        )
        ctx = montar_evolucao_faturamento(empresa_id, ev_de, ev_mes_de, ev_ate, ev_mes_ate)
        ctx['ev_periodo_aviso'] = ev_aviso
        return ctx
    return {}


def montar_html_relatorio_apresentacao(request, empresa, ano: int, mes: int) -> str:
    secoes: list[dict] = []
    for modelo in MODELOS_ANALISE:
        ctx = _contexto_modelo(empresa.pk, request, ano, mes, modelo.codigo)
        ctx['apresentacao'] = True
        html = render_to_string(modelo.template_partial, ctx, request=request)
        secoes.append({
            'codigo': modelo.codigo,
            'titulo_pill': modelo.titulo,
            'html': html,
        })

    return render_to_string(
        'dashboard/analise_relatorio_apresentacao.html',
        {
            'empresa': empresa,
            'secoes': secoes,
            'mes_filtro': f'{ano:04d}-{mes:02d}',
        },
        request=request,
    )
