"""Monta contexto dos relatórios mensais da aba Análises."""
from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from dashboard.analises_catalogo import (
    MODELOS_ANALISE,
    modelo_analise_ativo,
    modelo_analise_padrao,
)
from faturamento_medico.dashboard_exames import (
    _convenios_disponiveis_empresa,
    _fmt_card_dashboard,
    _fmt_moeda_br,
    montar_contexto_dashboard_producao,
    montar_dashboard_exames,
)


def _convenios_request(request) -> list[str]:
    return [c.strip() for c in request.GET.getlist('convenio') if c and str(c).strip()]


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
    }

    convenios_sel = _convenios_request(request)
    ctx['convenios_disponiveis'] = _convenios_disponiveis_empresa(empresa_id)
    ctx['filtros'] = {'convenios': convenios_sel}

    if modelo.codigo == 'exames_convenio':
        ctx.update(_contexto_exames_convenio(empresa_id, ano, mes, convenios_sel))
    elif modelo.codigo == 'producao_conferencia':
        ctx.update(_contexto_producao_conferencia(request, empresa_id, mes_filtro, regime))

    return ctx


def _contexto_exames_convenio(
    empresa_id: int,
    ano: int,
    mes: int,
    convenios_sel: list[str],
) -> dict:
    dados = montar_dashboard_exames(empresa_id, ano, mes, convenios=convenios_sel)
    totais = dict(dados['totais_gerais'])
    totais['total_valor_fmt'] = _fmt_moeda_br(totais['total_valor'])
    totais['status_linhas'] = [
        {**linha, 'valor_fmt': _fmt_moeda_br(linha['valor'])}
        for linha in totais['status_linhas']
    ]

    params_listagem = [
        ('data_inicio', dados['data_inicio']),
        ('data_fim', dados['data_fim']),
    ]
    for conv in convenios_sel:
        params_listagem.append(('convenio', conv))

    return {
        'mes_label': dados['mes_label'],
        'data_inicio': dados['data_inicio'],
        'data_fim': dados['data_fim'],
        'cards_convenio': [_fmt_card_dashboard(c) for c in dados['cards']],
        'totais_gerais': totais,
        'url_listagem_mes': f"{reverse('faturamento_medico:ftlistar')}?{urlencode(params_listagem)}",
    }


def _contexto_producao_conferencia(
    request,
    empresa_id: int,
    mes_filtro: str,
    regime: str,
) -> dict:
    prod = montar_contexto_dashboard_producao(request, empresa_id)
    q = [('mes', mes_filtro)]
    for conv in prod.get('filtros', {}).get('convenios') or []:
        q.append(('convenio', conv))
    for d in prod.get('dias_selecionados') or []:
        q.append(('dia', d))
    prod['url_producao_tela_cheia'] = (
        f"{reverse('faturamento_medico:dashboard_exames_diario')}?{urlencode(q)}"
    )
    prod['mes_filtro'] = mes_filtro
    prod['regime'] = regime
    prod['dash_aba'] = 'analises'
    prod['modelo_analise'] = 'producao_conferencia'
    return prod
