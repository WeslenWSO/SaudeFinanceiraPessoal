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


def _modalidade_item(faturamento, item=None):
    if item and item.modalidade:
        return item.modalidade
    obs = faturamento.observacao or ''
    if 'Modalidade:' in obs:
        for parte in obs.splitlines():
            if parte.strip().lower().startswith('modalidade:'):
                valor = parte.split(':', 1)[-1].strip()
                if valor:
                    return valor
    return '-'


def montar_contexto_relatorio_lote(lote_id, empresa_id, *, layout='padrao'):
    lote = _validar_acesso_lote(lote_id, empresa_id)
    empresa = Empresa.objects.get(id=empresa_id)

    faturamentos = FaturamentoMedico.objects.filter(lote=str(lote.id)).order_by('data', 'guia', 'nome')
    items = (
        ItemServico.objects.filter(faturamento__in=faturamentos)
        .select_related('faturamento')
        .order_by('faturamento__data', 'faturamento__nome', 'faturamento__guia', 'id')
    )

    periodo_inicio = faturamentos.aggregate(min_data=Min('data'))['min_data']
    periodo_fim = faturamentos.aggregate(max_data=Max('data'))['max_data']
    total_geral = Decimal('0')

    if layout == 'publico':
        linhas = []
        for item in items:
            fat = item.faturamento
            valor_item = item.total if item.total is not None else (item.valor or Decimal('0'))
            linhas.append({
                'data': fat.data,
                'paciente': fat.nome or '-',
                'nome_associado': fat.nome_associado or fat.nome or '-',
                'guia': fat.guia or '-',
                'procedimento': item.servico or '-',
                'modalidade': _modalidade_item(fat, item),
                'com_contraste': item.com_contraste,
                'valor': valor_item,
            })
            total_geral += valor_item
        grouped_rows = linhas
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
        'linhas': grouped_rows if layout == 'publico' else [],
        'total_geral': total_geral,
        'data_emissao_relatorio': timezone.now().date(),
        'layout': layout,
        'usa_layout_publico': convenio_usa_layout_publico(lote.convenio),
    }
