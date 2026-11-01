"""Visão Faturamento no dashboard — NFSe emitidas (serviços), gráfico por categoria."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from notasfiscais.models import NotaFiscalServico


def _fmt_moeda(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return '0,00'
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _fmt_numero_int(valor: int) -> str:
    return f'{valor:,}'.replace(',', '.')


def _fmt_percentual(parte: Decimal, total: Decimal) -> str:
    if not total:
        return '0,00%'
    pct = (parte / total) * Decimal('100')
    return f'{pct:.2f}'.replace('.', ',') + '%'


def _rotulo_categoria(descricao_regra: str | None, base_servico: str | None) -> str:
    cat = (descricao_regra or '').strip()
    if cat:
        return cat
    bs = (base_servico or 'NORMAL').upper()
    if bs == 'DEMAIS':
        return 'Sem regra · Base demais'
    return 'Sem regra · Base normal'


def _linhas_de_agregacao(
    rows,
    *,
    rotulo_fn,
    total_valor: Decimal,
) -> list[dict]:
    linhas = []
    for row in rows:
        valor = Decimal(str(row.get('valor') or 0))
        qtd = int(row.get('quantidade') or 0)
        linhas.append(
            {
                'rotulo': rotulo_fn(row),
                'quantidade': qtd,
                'quantidade_fmt': _fmt_numero_int(qtd),
                'valor': valor,
                'valor_fmt': _fmt_moeda(valor),
                'percentual_fmt': _fmt_percentual(valor, total_valor),
            }
        )
    return linhas


def _chart_json(linhas: list[dict]) -> tuple[str, str]:
    labels = [ln['rotulo'] for ln in linhas]
    valores = [float(ln['valor']) for ln in linhas]
    return json.dumps(labels, ensure_ascii=False), json.dumps(valores)


def montar_visao_faturamento(
    empresa_id: int,
    ano: int,
    mes: int,
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict:
    from dashboard.periodo_dashboard import resolver_inicio_fim

    inicio, fim = resolver_inicio_fim(ano, mes, data_inicio=data_inicio, data_fim=data_fim)

    qs = NotaFiscalServico.objects.filter(
        empresa_id=empresa_id,
        data_emissao__gte=inicio,
        data_emissao__lte=fim,
        data_cancelamento__isnull=True,
    )

    total_notas = qs.count()
    agg = qs.aggregate(
        total_bruto=Sum('valor_bruto'),
        dias_emissao=Count('data_emissao', distinct=True),
    )
    total_valor = Decimal(str(agg['total_bruto'] or 0))
    dias_com_nota = int(agg['dias_emissao'] or 0)

    ticket_medio = (total_valor / total_notas) if total_notas else Decimal('0')
    media_dia = (total_valor / dias_com_nota) if dias_com_nota else Decimal('0')

    por_regra = (
        qs.values(
            'codigo_da_regra_do_imposto__DescricaoRegraImposto',
            'base_servico',
        )
        .annotate(
            quantidade=Count('id'),
            valor=Sum('valor_bruto'),
        )
        .order_by('-valor')
    )

    linhas_categoria = _linhas_de_agregacao(
        por_regra,
        rotulo_fn=lambda row: _rotulo_categoria(
            row.get('codigo_da_regra_do_imposto__DescricaoRegraImposto'),
            row.get('base_servico'),
        ),
        total_valor=total_valor,
    )
    for ln in linhas_categoria:
        ln['categoria'] = ln['rotulo']

    por_forma = (
        qs.values('forma_pagamento__descricao')
        .annotate(
            quantidade=Count('id'),
            valor=Sum('valor_bruto'),
        )
        .order_by('-valor')
    )
    linhas_forma_pagamento = _linhas_de_agregacao(
        por_forma,
        rotulo_fn=lambda row: (row.get('forma_pagamento__descricao') or '').strip()
        or 'Sem forma definida',
        total_valor=total_valor,
    )
    for ln in linhas_forma_pagamento:
        ln['forma_pagamento'] = ln['rotulo']

    por_cliente = (
        qs.values('cliente')
        .annotate(
            quantidade=Count('id'),
            valor=Sum('valor_bruto'),
        )
        .order_by('-valor')[:10]
    )
    linhas_top_clientes = _linhas_de_agregacao(
        por_cliente,
        rotulo_fn=lambda row: (row.get('cliente') or 'Cliente não informado').strip()[:200],
        total_valor=total_valor,
    )
    for ln in linhas_top_clientes:
        ln['cliente'] = ln['rotulo']

    cat_labels_json, cat_data_json = _chart_json(linhas_categoria)
    fp_labels_json, fp_data_json = _chart_json(linhas_forma_pagamento)
    cli_labels_json, cli_data_json = _chart_json(linhas_top_clientes)

    return {
        'data_inicio': inicio.isoformat(),
        'data_fim': fim.isoformat(),
        'kpi_faturamento_total_fmt': _fmt_moeda(total_valor),
        'kpi_notas_fmt': _fmt_numero_int(total_notas),
        'kpi_ticket_medio_fmt': _fmt_moeda(ticket_medio),
        'kpi_media_dia_fmt': _fmt_moeda(media_dia),
        'dias_com_emissao': dias_com_nota,
        'linhas_categoria': linhas_categoria,
        'linhas_forma_pagamento': linhas_forma_pagamento,
        'linhas_top_clientes': linhas_top_clientes,
        'total_quantidade': total_notas,
        'total_quantidade_fmt': _fmt_numero_int(total_notas),
        'total_valor_fmt': _fmt_moeda(total_valor),
        'total_percentual_fmt': '100%' if total_valor else '0%',
        'tem_dados': total_valor > 0,
        'chart_categoria_labels_json': cat_labels_json,
        'chart_categoria_data_json': cat_data_json,
        'chart_forma_pagamento_labels_json': fp_labels_json,
        'chart_forma_pagamento_data_json': fp_data_json,
        'chart_top_clientes_labels_json': cli_labels_json,
        'chart_top_clientes_data_json': cli_data_json,
    }
