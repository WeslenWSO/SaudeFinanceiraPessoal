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
    'GEAP',
    'POSTAL',
)

CONVENIOS_RELATORIO_COLUNA_GUIA = (
    'FUSEX',
    'POLICIA MILITAR',
    'POLÍCIA MILITAR',
)

MESES_PT = (
    '',
    'JANEIRO',
    'FEVEREIRO',
    'MARÇO',
    'ABRIL',
    'MAIO',
    'JUNHO',
    'JULHO',
    'AGOSTO',
    'SETEMBRO',
    'OUTUBRO',
    'NOVEMBRO',
    'DEZEMBRO',
)

# Ordem do resumo no modelo PP Saúde / convênios públicos
RESUMO_MODALIDADES_PUBLICO = (
    ('MG', 'QUANTIDADE DE MAMOGRAFIA'),
    ('CT', 'QUANTIDADE DE TOMOGRAFIA'),
    ('US', 'QUANTIDADE DE ULTRASSONOGRAFIA'),
    ('CR', 'QUANTIDADE DE RAIO X'),
    ('MR', 'QUANTIDADE DE RESSONÂNCIA'),
    ('EG', 'QUANTIDADE DE ELETROENCEFALOGRAMA'),
    ('EC', 'QUANTIDADE DE ELETROCARDIOGRAMA'),
)


def convenio_usa_layout_publico(nome_convenio: str) -> bool:
    nome = (nome_convenio or '').upper()
    return any(palavra in nome for palavra in CONVENIOS_LAYOUT_PUBLICO_KEYWORDS)


def convenio_relatorio_coluna_guia(nome_convenio: str) -> bool:
    """FUSEX e PM exibem número da guia; Bombeiro e PP Saúde exibem associado."""
    nome = (nome_convenio or '').upper().strip()
    if any(palavra in nome for palavra in CONVENIOS_RELATORIO_COLUNA_GUIA):
        return True
    if nome == 'PM' or nome.startswith('PM ') or nome.endswith(' PM') or ' PM ' in f' {nome} ':
        return True
    return False


def _validar_acesso_lote(lote_id, empresa_id):
    lote = Lote.objects.get(id=lote_id)
    if lote.empresa_id != int(empresa_id):
        raise PermissionError('Acesso negado')
    return lote


def _validar_acesso_lotes(lote_ids, empresa_id):
    ids = [int(i) for i in lote_ids]
    lotes = list(Lote.objects.filter(id__in=ids, empresa_id=int(empresa_id)).order_by('-id'))
    if len(lotes) != len(ids):
        raise Lote.DoesNotExist
    return lotes


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
    return _inferir_modalidade(item.servico if item else faturamento.servico, '')


def _inferir_modalidade(procedimento, modalidade):
    mod = (modalidade or '').strip().upper()
    if mod and mod != '-':
        if mod == 'RX':
            return 'CR'
        return mod
    p = (procedimento or '').lower()
    if p.startswith('rm ') or 'resson' in p:
        return 'MR'
    if p.startswith('tc ') or 'tomograf' in p:
        return 'CT'
    if (
        p.startswith('us ')
        or 'ultrassom' in p
        or 'ultrassonograf' in p
        or 'doppler' in p
    ):
        return 'US'
    if p.startswith('rx ') or ' raio' in p or p.startswith('raio'):
        return 'CR'
    if 'mamograf' in p:
        return 'MG'
    if 'eletrocardiograma' in p or p.startswith('ecg'):
        return 'EC'
    if 'eletroencefalograma' in p or p.startswith('eeg'):
        return 'EG'
    return '-'


def _normalizar_codigo_modalidade(codigo):
    mod = (codigo or '').strip().upper()
    if mod == 'RX':
        return 'CR'
    return mod


def _montar_resumo_publico(linhas):
    contagem = {codigo: 0 for codigo, _ in RESUMO_MODALIDADES_PUBLICO}
    quantidade_total = 0
    valor_total = Decimal('0')
    for linha in linhas:
        quantidade_total += 1
        valor_total += linha.get('valor') or Decimal('0')
        codigo = _normalizar_codigo_modalidade(linha.get('modalidade'))
        if codigo in contagem:
            contagem[codigo] += 1
    resumo_modalidades = [
        {'codigo': codigo, 'label': label, 'quantidade': contagem[codigo]}
        for codigo, label in RESUMO_MODALIDADES_PUBLICO
    ]
    return {
        'modalidades': resumo_modalidades,
        'quantidade_total': quantidade_total,
        'valor_total': valor_total,
    }


def _mes_referencia_label(data_ref):
    if not data_ref:
        return ''
    mes = MESES_PT[data_ref.month] if 1 <= data_ref.month <= 12 else ''
    return f'{mes} {data_ref.year}' if mes else str(data_ref.year)


def _local_empresa(empresa):
    """Primeira linha do endereço da empresa para o campo Local do rodapé."""
    endereco = (empresa.endereco or '').strip()
    if not endereco:
        return ''
    return endereco.splitlines()[0].strip()


def montar_contexto_relatorio_lote(lote_id, empresa_id, *, layout='padrao', lote_ids=None):
    from .lote_utils import parse_lote_ids

    ids = parse_lote_ids(lote_ids) if lote_ids else parse_lote_ids(lote_id)
    if not ids:
        raise Lote.DoesNotExist
    lotes = _validar_acesso_lotes(ids, empresa_id)
    lote = lotes[0]
    empresa = Empresa.objects.get(id=empresa_id)

    chaves_lote = [str(lid) for lid in ids]
    faturamentos = FaturamentoMedico.objects.filter(lote__in=chaves_lote).order_by('data', 'guia', 'nome')
    items = (
        ItemServico.objects.filter(faturamento__in=faturamentos)
        .select_related('faturamento')
        .order_by('faturamento__data', 'faturamento__nome', 'faturamento__guia', 'id')
    )

    periodo_inicio = faturamentos.aggregate(min_data=Min('data'))['min_data']
    periodo_fim = faturamentos.aggregate(max_data=Max('data'))['max_data']
    total_geral = Decimal('0')
    resumo_publico = None
    mes_referencia = _mes_referencia_label(periodo_fim or lote.data_lote)

    if layout == 'publico':
        linhas = []
        for item in items:
            fat = item.faturamento
            valor_item = item.total if item.total is not None else (item.valor or Decimal('0'))
            modalidade = _modalidade_item(fat, item)
            linhas.append({
                'data': fat.data,
                'paciente': fat.nome or '-',
                'nome_associado': fat.nome_associado or fat.nome or '-',
                'numero_guia': (fat.guia or '').strip() or '-',
                'procedimento': item.servico or '-',
                'modalidade': modalidade,
                'com_contraste': item.com_contraste,
                'valor': valor_item,
            })
            total_geral += valor_item
        resumo_publico = _montar_resumo_publico(linhas)
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
        'local_relatorio': _local_empresa(empresa),
        'periodo_inicio': periodo_inicio,
        'periodo_fim': periodo_fim,
        'mes_referencia': mes_referencia,
        'grouped_items': grouped_rows if layout == 'publico' else grouped_items,
        'linhas': grouped_rows if layout == 'publico' else [],
        'resumo_publico': resumo_publico,
        'total_geral': total_geral,
        'data_emissao_relatorio': timezone.now().date(),
        'layout': layout,
        'usa_layout_publico': convenio_usa_layout_publico(lote.convenio),
        'coluna_terceira_guia': convenio_relatorio_coluna_guia(lote.convenio) if layout == 'publico' else False,
    }
