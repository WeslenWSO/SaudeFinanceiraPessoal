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


def montar_visao_faturamento(empresa_id: int, ano: int, mes: int) -> dict:
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])

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

    linhas = []
    for row in por_regra:
        valor = Decimal(str(row['valor'] or 0))
        qtd = int(row['quantidade'] or 0)
        linhas.append(
            {
                'categoria': _rotulo_categoria(
                    row.get('codigo_da_regra_do_imposto__DescricaoRegraImposto'),
                    row.get('base_servico'),
                ),
                'quantidade': qtd,
                'quantidade_fmt': _fmt_numero_int(qtd),
                'valor': valor,
                'valor_fmt': _fmt_moeda(valor),
                'percentual_fmt': _fmt_percentual(valor, total_valor),
            }
        )

    labels = [ln['categoria'] for ln in linhas]
    valores = [float(ln['valor']) for ln in linhas]

    return {
        'titulo_periodo_nfse': mes_titulo,
        'data_inicio': inicio.isoformat(),
        'data_fim': fim.isoformat(),
        'kpi_faturamento_total_fmt': _fmt_moeda(total_valor),
        'kpi_notas_fmt': _fmt_numero_int(total_notas),
        'kpi_ticket_medio_fmt': _fmt_moeda(ticket_medio),
        'kpi_media_dia_fmt': _fmt_moeda(media_dia),
        'dias_com_emissao': dias_com_nota,
        'linhas_categoria': linhas,
        'total_quantidade': total_notas,
        'total_quantidade_fmt': _fmt_numero_int(total_notas),
        'total_valor_fmt': _fmt_moeda(total_valor),
        'total_percentual_fmt': '100%' if total_valor else '0%',
        'tem_dados': total_valor > 0,
        'chart_categoria_labels_json': json.dumps(labels, ensure_ascii=False),
        'chart_categoria_data_json': json.dumps(valores),
    }
