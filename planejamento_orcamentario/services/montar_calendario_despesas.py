"""Calendário mensal com soma das despesas planejadas por dia."""

from __future__ import annotations

import calendar as cal_mod
from collections import defaultdict
from datetime import date
from decimal import Decimal

from planejamento_orcamentario.models import ItemOrcamento, LancamentoOrcamento

_MESES_NOME = (
    '',
    'Janeiro',
    'Fevereiro',
    'Março',
    'Abril',
    'Maio',
    'Junho',
    'Julho',
    'Agosto',
    'Setembro',
    'Outubro',
    'Novembro',
    'Dezembro',
)

TIPOS_DESPESA = {
    ItemOrcamento.TIPO_FIXA,
    ItemOrcamento.TIPO_SEMI_FIXA,
    ItemOrcamento.TIPO_VARIAVEL,
    ItemOrcamento.TIPO_IMPOSTO,
}


def _detalhe_lancamento(lanc: LancamentoOrcamento) -> dict:
    item = lanc.item
    meta = ItemOrcamento.tipo_meta(item.tipo)
    return {
        'nome': item.nome,
        'valor': lanc.valor or Decimal('0'),
        'tipo': item.tipo,
        'tipo_label': meta['titulo'],
        'tipo_cor': meta['cor'],
        'categoria': item.categoria.nome if item.categoria_id else '',
        'item_id': item.pk,
    }


def montar_calendario_despesas(empresa, ano: int, mes: int) -> dict:
    ultimo_dia = cal_mod.monthrange(ano, mes)[1]
    data_ini = date(ano, mes, 1)
    data_fim = date(ano, mes, ultimo_dia)

    lancamentos = (
        LancamentoOrcamento.objects.filter(
            empresa=empresa,
            item__ativo=True,
            item__tipo__in=TIPOS_DESPESA,
            data_lancamento__gte=data_ini,
            data_lancamento__lte=data_fim,
        )
        .select_related('item', 'item__categoria')
        .order_by('data_lancamento', 'item__nome')
    )

    totais_dia: dict[date, Decimal] = defaultdict(lambda: Decimal('0'))
    itens_dia: dict[date, list] = defaultdict(list)
    for lanc in lancamentos:
        totais_dia[lanc.data_lancamento] += lanc.valor or Decimal('0')
        itens_dia[lanc.data_lancamento].append(_detalhe_lancamento(lanc))

    semanas = []
    for semana in cal_mod.monthcalendar(ano, mes):
        dias = []
        for dia_num in semana:
            if dia_num == 0:
                dias.append({'numero': 0, 'fora_mes': True})
                continue
            d = date(ano, mes, dia_num)
            total = totais_dia.get(d, Decimal('0'))
            detalhes = itens_dia.get(d, [])
            dias.append({
                'numero': dia_num,
                'data': d,
                'data_iso': d.isoformat(),
                'fora_mes': False,
                'hoje': d == date.today(),
                'domingo': d.weekday() == 6,
                'total': total,
                'tem_valor': total > 0,
                'qtd': len(detalhes),
                'detalhes': detalhes,
            })
        semanas.append(dias)

    mes_anterior = mes - 1 if mes > 1 else 12
    ano_anterior = ano if mes > 1 else ano - 1
    mes_proximo = mes + 1 if mes < 12 else 1
    ano_proximo = ano if mes < 12 else ano + 1

    total_mes = sum(totais_dia.values(), Decimal('0'))
    dias_com_despesa = len([d for d, t in totais_dia.items() if t > 0])

    detalhes_por_dia = {
        d.isoformat(): [
            {
                'nome': it['nome'],
                'tipo_label': it['tipo_label'],
                'tipo_cor': it['tipo_cor'],
                'categoria': it['categoria'],
                'valor': float(it['valor']),
            }
            for it in itens_dia[d]
        ]
        for d in sorted(itens_dia.keys())
    }

    return {
        'ano': ano,
        'mes': mes,
        'mes_nome': _MESES_NOME[mes],
        'mes_anterior': mes_anterior,
        'ano_anterior': ano_anterior,
        'mes_proximo': mes_proximo,
        'ano_proximo': ano_proximo,
        'semanas': semanas,
        'total_mes': total_mes,
        'dias_com_despesa': dias_com_despesa,
        'qtd_lancamentos': lancamentos.count(),
        'detalhes_por_dia': detalhes_por_dia,
    }
