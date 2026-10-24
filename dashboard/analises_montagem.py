"""Monta contexto dos relatórios mensais da aba Análises."""
from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from dashboard.analise_faturamento_convenio import montar_relatorio_faturamento_convenio
from dashboard.analise_detalhes_modalidade_convenio import montar_detalhes_modalidade_convenio
from dashboard.analise_faturamento_modalidade import montar_relatorio_faturamento_modalidade
from dashboard.analises_catalogo import (
    MODELOS_ANALISE,
    modelo_analise_ativo,
    modelo_analise_padrao,
)
from faturamento_medico.dashboard_exames import (
    _convenios_disponiveis_empresa,
    _fmt_card_dashboard,
    _fmt_moeda_br,
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

    if modelo.codigo == 'faturamento_convenio':
        ctx.update(montar_relatorio_faturamento_convenio(empresa_id, ano, mes))
    elif modelo.codigo == 'faturamento_modalidade':
        ctx.update(montar_relatorio_faturamento_modalidade(empresa_id, ano, mes))
    elif modelo.codigo == 'detalhes_modalidade_convenio':
        ctx.update(montar_detalhes_modalidade_convenio(empresa_id, ano, mes))
    elif modelo.codigo == 'exames_convenio':
        ctx.update(_contexto_exames_convenio(empresa_id, ano, mes, convenios_sel))

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
