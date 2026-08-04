"""Montagem de contexto para relatórios de impressão de lote."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from django.db.models import Max, Min
from django.utils import timezone

from empresa.models import Empresa

from .models import FaturamentoMedico, ItemServico, Lote

CONVENIOS_LAYOUT_PUBLICO_KEYWORDS = (
    'FUSEX',
    'POLICIA MILITAR',
    'POLÍCIA MILITAR',
    'CORPO DE BOMBEIRO',
    'BOMBEIRO',
    'PP SAUDE',
    'PP SAÚDE',
)


def convenio_usa_layout_publico(nome_convenio: str) -> bool:
    nome = (nome_convenio or '').upper()
    return any(palavra in nome for palavra in CONVENIOS_LAYOUT_PUBLICO_KEYWORDS)


def _validar_acesso_lote(lote_id, empresa_id):
    lote = Lote.objects.get(id=lote_id)
    if lote.empresa_id != int(empresa_id):
        raise PermissionError('Acesso negado')
    return lote


def montar_contexto_relatorio_lote(lote_id, empresa_id, *, layout='padrao'):
    lote = _validar_acesso_lote(lote_id, empresa_id)
    empresa = Empresa.objects.get(id=empresa_id)

    faturamentos = FaturamentoMedico.objects.filter(lote=str(lote.id)).order_by('data', 'guia', 'nome')
    items = (
        ItemServico.objects.filter(faturamento__in=faturamentos)
        .select_related('faturamento')
        .order_by('faturamento__guia', 'faturamento__data', 'faturamento__nome', 'id')
    )

    periodo_inicio = faturamentos.aggregate(min_data=Min('data'))['min_data']
    periodo_fim = faturamentos.aggregate(max_data=Max('data'))['max_data']
    total_geral = Decimal('0')

    if layout == 'publico':
        grouped_items = OrderedDict()
        for item in items:
            fat = item.faturamento
            chave = (fat.guia or '-', fat.nome or 'Sem Nome')
            if chave not in grouped_items:
                grouped_items[chave] = {
                    'guia': fat.guia or '-',
                    'carteirinha': fat.carteirinha or '-',
                    'beneficiario': fat.nome or '-',
                    'data': fat.data,
                    'itens': [],
                    'subtotal': Decimal('0'),
                }
            grouped_items[chave]['itens'].append(item)
            sub = item.total or Decimal('0')
            grouped_items[chave]['subtotal'] += sub
            total_geral += sub
        grouped_rows = list(grouped_items.values())
    else:
        grouped_items = OrderedDict()
        for item in items:
            beneficiario = item.faturamento.nome or 'Sem Nome'
            grouped_items.setdefault(beneficiario, []).append(item)
            total_geral += item.total or Decimal('0')
        grouped_rows = grouped_items

    return {
        'lote': lote,
        'empresa': empresa,
        'convenio_nome': lote.convenio or '',
        'periodo_inicio': periodo_inicio,
        'periodo_fim': periodo_fim,
        'grouped_items': grouped_rows if layout == 'publico' else grouped_items,
        'total_geral': total_geral,
        'data_emissao_relatorio': timezone.now().date(),
        'layout': layout,
        'usa_layout_publico': convenio_usa_layout_publico(lote.convenio),
    }
