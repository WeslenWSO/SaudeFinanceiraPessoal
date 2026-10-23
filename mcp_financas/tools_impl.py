"""Implementação das tools (consultas read-only ao banco Django)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from mcp_financas.django_setup import setup_django


def _json(data) -> str:
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, date):
            return o.isoformat()
        raise TypeError(type(o))

    return json.dumps(data, ensure_ascii=False, indent=2, default=default)


def _parse_date(s: str, *, field: str) -> date:
    s = (s or '').strip()
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f'{field} inválida (use AAAA-MM-DD): {s!r}') from exc


def health_check() -> str:
    setup_django()
    from django.db import connection

    connection.ensure_connection()
    return _json({'ok': True, 'service': 'mcp-financas', 'database': connection.vendor})


def listar_empresas(apenas_ativas: bool = True) -> str:
    setup_django()
    from empresa.models import Empresa

    qs = Empresa.objects.all().order_by('razao')
    if apenas_ativas:
        qs = qs.filter(status='Ativa')
    rows = [
        {
            'id': e.pk,
            'razao': e.razao,
            'nome_fantasia': e.nome_fantasia or '',
            'cnpj': e.cnpj,
            'status': e.status,
        }
        for e in qs[:100]
    ]
    return _json({'empresas': rows, 'total': len(rows)})


def resumo_faturamento(
    empresa_id: int,
    data_inicio: str,
    data_fim: str,
) -> str:
    setup_django()
    from empresa.models import Empresa
    from faturamento_medico.models import FaturamentoMedico, ItemServico

    di = _parse_date(data_inicio, field='data_inicio')
    df = _parse_date(data_fim, field='data_fim')
    if df < di:
        raise ValueError('data_fim deve ser >= data_inicio')

    empresa = Empresa.objects.filter(pk=empresa_id).first()
    if not empresa:
        raise ValueError(f'Empresa id={empresa_id} não encontrada')

    qs = FaturamentoMedico.objects.filter(
        empresa_id=empresa_id,
        data__gte=di,
        data__lte=df,
    )
    total_faturamentos = qs.count()
    itens = ItemServico.objects.filter(faturamento__in=qs)
    agg = itens.aggregate(
        procedimentos=Count('id'),
        valor_itens=Sum('total'),
        valor_alt=Sum('valor'),
    )
    valor = agg['valor_itens'] or agg['valor_alt'] or Decimal('0')

    por_convenio = (
        qs.values('convenio')
        .annotate(qtd=Count('id'))
        .order_by('-qtd')[:15]
    )

    return _json(
        {
            'empresa': {'id': empresa.pk, 'razao': empresa.razao},
            'periodo': {'inicio': di.isoformat(), 'fim': df.isoformat()},
            'faturamentos': total_faturamentos,
            'procedimentos': agg['procedimentos'] or 0,
            'valor_total_estimado': valor,
            'top_convenios_por_faturamentos': list(por_convenio),
        }
    )


def resumo_fluxo_caixa(empresa_id: int, ano: int) -> str:
    setup_django()
    from empresa.models import Empresa
    from fluxo_de_caixa.services.montar_fluxo_mensal import (
        MESES_CURTO,
        montar_grafico_planilha,
        montar_linhas_planilha,
    )

    empresa = Empresa.objects.filter(pk=empresa_id).first()
    if not empresa:
        raise ValueError(f'Empresa id={empresa_id} não encontrada')
    if ano < 2000 or ano > 2100:
        raise ValueError('ano inválido')

    linhas = montar_linhas_planilha(empresa, ano)
    graf = montar_grafico_planilha(linhas, ano)
    labels = [f'{MESES_CURTO[m - 1]}/{ano}' for m in range(1, 13)]

    def _loads(key):
        raw = graf.get(key)
        if raw is None:
            return []
        if isinstance(raw, str):
            return json.loads(raw)
        return list(raw)

    receitas = _loads('receitas_json')
    despesas = _loads('despesas_json')
    resultado = _loads('resultado_json')

    meses = []
    for i, lab in enumerate(labels):
        meses.append(
            {
                'mes': lab,
                'receitas': receitas[i] if i < len(receitas) else 0,
                'despesas': despesas[i] if i < len(despesas) else 0,
                'resultado': resultado[i] if i < len(resultado) else 0,
            }
        )

    return _json(
        {
            'empresa': {'id': empresa.pk, 'razao': empresa.razao},
            'ano': ano,
            'meses': meses,
            'tem_dados': graf.get('tem_dados', False),
        }
    )


TOOL_REGISTRY = {
    'health_check': health_check,
    'listar_empresas': listar_empresas,
    'resumo_faturamento': resumo_faturamento,
    'resumo_fluxo_caixa': resumo_fluxo_caixa,
}


def executar_tool(nome: str, argumentos: dict | None) -> str:
    fn = TOOL_REGISTRY.get(nome)
    if fn is None:
        raise ValueError(f'Tool desconhecida: {nome}')
    args = argumentos or {}
    return fn(**args)
