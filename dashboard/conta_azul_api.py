"""Fachada legada — delega ao client Conta Azul por empresa."""

from __future__ import annotations

from datetime import date

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from empresa.models import Empresa


def _client(empresa_id: int) -> ContaAzulClient:
    empresa = Empresa.objects.get(pk=empresa_id)
    return ContaAzulClient.para_empresa(empresa)


def get_categorias(empresa_id: int):
    return _client(empresa_id).buscar_categorias()


def get_transacoes(empresa_id: int, data_inicio=None, data_fim=None):
    client = _client(empresa_id)
    params = {'pagina': 1, 'tamanho_pagina': 100}
    if data_inicio:
        params['data_vencimento_de'] = data_inicio
    if data_fim:
        params['data_vencimento_ate'] = data_fim
    return client.buscar_receitas(**params)


def buscar_contas_a_receber(empresa_id: int, filtros=None):
    return _client(empresa_id).buscar_receitas(**(filtros or {}))


def calcular_dre(empresa_id: int, data_inicio=None, data_fim=None):
    try:
        receitas = buscar_contas_a_receber(
            empresa_id,
            {
                'data_vencimento_de': data_inicio,
                'data_vencimento_ate': data_fim,
                'pagina': 1,
                'tamanho_pagina': 200,
            },
        )
        despesas = _client(empresa_id).buscar_despesas(
            data_vencimento_de=data_inicio,
            data_vencimento_ate=data_fim,
            pagina=1,
            tamanho_pagina=200,
        )
    except ContaAzulAPIError as exc:
        raise RuntimeError(str(exc)) from exc

    total_rec = sum(float(r.get('valor') or r.get('total') or 0) for r in receitas)
    total_desp = sum(float(d.get('valor') or d.get('total') or 0) for d in despesas)
    return {
        'receitas': total_rec,
        'despesas': total_desp,
        'lucro': total_rec - total_desp,
        'categorias_receitas': {},
        'categorias_despesas': {},
    }


def calcular_dre_mensal(empresa_id: int, ano: int | None = None):
    ano = ano or date.today().year
    meses = []
    for mes in range(1, 13):
        data_inicio = f'{ano}-{mes:02d}-01'
        if mes == 12:
            data_fim = f'{ano}-12-31'
        else:
            data_fim = f'{ano}-{mes+1:02d}-01'
        dre_mes = calcular_dre(empresa_id, data_inicio, data_fim)
        dre_mes['mes'] = mes
        dre_mes['ano'] = ano
        meses.append(dre_mes)
    return meses
