"""Agregação para o dashboard de exames por convênio e status de conferência."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.urls import reverse
from urllib.parse import urlencode

from .lote_utils import faturamento_tem_lote_interno, ids_lotes_internos
from .models import FaturamentoMedico, ItemServico, LogStatusConferenciaItem

STATUS_AGENDAMENTO_CANCELADOS = (
    'Cancelado',
    'Desistência',
    'Desistencia',
    'Deletado',
    'Deleção',
    'Delecao',
)

MESES_PT = (
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


def _q_cancelados():
    q = Q()
    for status in STATUS_AGENDAMENTO_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _status_linha(faturamento, item=None, ids_internos=None):
    tem_lote = faturamento_tem_lote_interno(faturamento, ids_internos=ids_internos)
    if item is not None:
        status_label, status_css = item.status_conferencia_badge()
        if tem_lote and (status_label in ('CONFERIDO', 'LOTE OK') or item.conferido):
            return 'LOTE OK', ItemServico.STATUS_CONFERENCIA_CSS['LOTE OK']
        return status_label, status_css
    if not (faturamento.guia or '').strip():
        return 'FALTA DE GUIA', ItemServico.STATUS_CONFERENCIA_CSS.get('FALTA DE GUIA', 'warning')
    if not faturamento.total:
        return 'FALTA DE VALOR NA TABELA', ItemServico.STATUS_CONFERENCIA_CSS.get(
            'FALTA DE VALOR NA TABELA', 'danger'
        )
    return 'PENDENTE', ItemServico.STATUS_CONFERENCIA_CSS['PENDENTE']


def _link_listagem(data_inicio, data_fim, convenio='', status='', nome=''):
    params = [
        ('data_inicio', data_inicio),
        ('data_fim', data_fim),
    ]
    if status:
        params.append(('status_conferencia', status))
    if convenio and convenio != 'Não informado':
        params.append(('convenio', convenio))
    if nome:
        params.append(('nome', nome))
    return f"{reverse('faturamento_medico:ftlistar')}?{urlencode(params)}"


def _chave_cliente(faturamento) -> str:
    nome = (faturamento.nome or '').strip()
    return nome.upper() if nome else '-'


def _acumular(stats, totais_gerais, convenio, status_label, valor, cliente_chave):
    stats[convenio][status_label]['quantidade'] += 1
    stats[convenio][status_label]['valor'] += valor
    stats[convenio][status_label]['clientes'].add(cliente_chave)
    totais_gerais[status_label]['quantidade'] += 1
    totais_gerais[status_label]['valor'] += valor
    totais_gerais[status_label]['clientes'].add(cliente_chave)


def _q_convenio_filtro(nome: str) -> Q:
    conv = (nome or '').strip()
    if not conv:
        return Q()
    return Q(convenio__iexact=conv)


def montar_dashboard_exames(empresa_id, ano, mes, convenios=None):
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    data_inicio = inicio.isoformat()
    data_fim = fim.isoformat()
    convenios_sel = [c.strip() for c in (convenios or []) if c and str(c).strip()]

    qs = (
        FaturamentoMedico.objects
        .filter(empresa_id=empresa_id, data__gte=inicio, data__lte=fim)
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )
    if convenios_sel:
        q_conv = Q()
        for conv in convenios_sel:
            q_conv |= _q_convenio_filtro(conv)
        qs = qs.filter(q_conv)

    ids_internos = ids_lotes_internos(empresa_id)
    stats = defaultdict(
        lambda: defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0'), 'clientes': set()}),
    )
    totais_gerais = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0'), 'clientes': set()})

    for fat in qs:
        conv = (fat.convenio or '').strip() or 'Não informado'
        cliente_chave = _chave_cliente(fat)
        itens = list(fat.itens_servico.all())
        if not itens:
            status_label, _ = _status_linha(fat, ids_internos=ids_internos)
            valor = Decimal(str(fat.total or 0))
            _acumular(stats, totais_gerais, conv, status_label, valor, cliente_chave)
            continue
        for item in itens:
            status_label, _ = _status_linha(fat, item, ids_internos=ids_internos)
            valor = item.total if item.total is not None else (item.valor or Decimal('0'))
            if not isinstance(valor, Decimal):
                valor = Decimal(str(valor))
            _acumular(stats, totais_gerais, conv, status_label, valor, cliente_chave)

    ordem_status = [c[0] for c in ItemServico.STATUS_CONFERENCIA_CHOICES]

    def _montar_linhas(bloco, convenio=None):
        linhas = []
        total_q = 0
        total_v = Decimal('0')
        clientes_bloco: set[str] = set()
        for st in ordem_status:
            d = bloco.get(st)
            if not d or d['quantidade'] == 0:
                continue
            clientes_bloco |= d['clientes']
            linhas.append({
                'status': st,
                'css': ItemServico.STATUS_CONFERENCIA_CSS.get(st, 'secondary'),
                'quantidade': d['quantidade'],
                'quantidade_clientes': len(d['clientes']),
                'valor': d['valor'],
                'url_listagem': _link_listagem(data_inicio, data_fim, convenio, st),
            })
            total_q += d['quantidade']
            total_v += d['valor']
        return linhas, total_q, total_v, len(clientes_bloco)

    cards = []
    for conv in stats.keys():
        linhas, total_q, total_v, total_clientes = _montar_linhas(stats[conv], convenio=conv)
        cards.append({
            'convenio': conv,
            'status_linhas': linhas,
            'total_quantidade': total_q,
            'total_clientes': total_clientes,
            'total_valor': total_v,
            'url_listagem': _link_listagem(data_inicio, data_fim, conv, ''),
        })
    cards.sort(key=lambda c: (-c['total_quantidade'], c['convenio'].lower()))

    geral_linhas, geral_q, geral_v, geral_clientes = _montar_linhas(totais_gerais)

    return {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'mes_label': f'{MESES_PT[mes]} / {ano}',
        'convenios_selecionados': convenios_sel,
        'cards': cards,
        'totais_gerais': {
            'status_linhas': geral_linhas,
            'total_quantidade': geral_q,
            'total_clientes': geral_clientes,
            'total_valor': geral_v,
        },
    }


def _ultimo_usuario_por_item(item_ids):
    """Mapa item_id -> último usuário que alterou status de conferência."""
    if not item_ids:
        return {}
    logs = (
        LogStatusConferenciaItem.objects
        .filter(item_servico_id__in=item_ids)
        .order_by('item_servico_id', '-data_hora', '-id')
        .values_list('item_servico_id', 'usuario_nome')
    )
    resultado = {}
    for item_id, nome in logs:
        if item_id not in resultado:
            resultado[item_id] = (nome or '').strip() or 'Sistema'
    return resultado


def _iterar_exames_dia(fat, usuarios_item):
    """Gera (convenio, usuario, cliente_chave) por exame/procedimento do faturamento."""
    conv = (fat.convenio or '').strip() or 'Não informado'
    cliente_chave = _chave_cliente(fat)
    itens = list(fat.itens_servico.all())
    if not itens:
        yield conv, 'Sem conferência', cliente_chave
        return
    for item in itens:
        usuario = usuarios_item.get(item.pk, 'Sem conferência')
        yield conv, usuario, cliente_chave


def _acumular_dia(stats, convenio, usuario, cliente_chave):
    stats[(convenio, usuario)]['quantidade'] += 1
    stats[(convenio, usuario)]['clientes'].add(cliente_chave)


def montar_resumo_regua_mes(empresa_id, ano, mes, convenios=None):
    """Totais de exames e clientes por dia do mês (para a régua temporal)."""
    inicio = date(ano, mes, 1)
    ultimo_dia = monthrange(ano, mes)[1]
    fim = date(ano, mes, ultimo_dia)
    convenios_sel = [c.strip() for c in (convenios or []) if c and str(c).strip()]

    qs = (
        FaturamentoMedico.objects
        .filter(empresa_id=empresa_id, data__gte=inicio, data__lte=fim)
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )
    if convenios_sel:
        q_conv = Q()
        for conv in convenios_sel:
            q_conv |= _q_convenio_filtro(conv)
        qs = qs.filter(q_conv)

    por_dia = defaultdict(lambda: {'quantidade': 0, 'clientes': set()})
    for fat in qs:
        dia = fat.data
        if not dia:
            continue
        cliente_chave = _chave_cliente(fat)
        itens = list(fat.itens_servico.all())
        if not itens:
            por_dia[dia]['quantidade'] += 1
            por_dia[dia]['clientes'].add(cliente_chave)
            continue
        for _item in itens:
            por_dia[dia]['quantidade'] += 1
            por_dia[dia]['clientes'].add(cliente_chave)

    dias = []
    for d in range(1, ultimo_dia + 1):
        ref = date(ano, mes, d)
        info = por_dia.get(ref, {'quantidade': 0, 'clientes': set()})
        dias.append({
            'dia': d,
            'data_iso': ref.isoformat(),
            'quantidade': info['quantidade'],
            'quantidade_clientes': len(info['clientes']),
        })
    return dias


def montar_dashboard_exames_diario(empresa_id, ano, mes, dia, convenios=None):
    """Detalhe de um dia: exames e clientes por convênio e usuário (última conferência)."""
    ultimo_dia = monthrange(ano, mes)[1]
    dia = max(1, min(int(dia or 1), ultimo_dia))
    dia_ref = date(ano, mes, dia)
    convenios_sel = [c.strip() for c in (convenios or []) if c and str(c).strip()]

    qs = (
        FaturamentoMedico.objects
        .filter(empresa_id=empresa_id, data=dia_ref)
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )
    if convenios_sel:
        q_conv = Q()
        for conv in convenios_sel:
            q_conv |= _q_convenio_filtro(conv)
        qs = qs.filter(q_conv)

    faturamentos = list(qs)
    item_ids = [
        item.pk
        for fat in faturamentos
        for item in fat.itens_servico.all()
    ]
    usuarios_item = _ultimo_usuario_por_item(item_ids)

    stats = defaultdict(lambda: {'quantidade': 0, 'clientes': set()})
    for fat in faturamentos:
        for conv, usuario, cliente in _iterar_exames_dia(fat, usuarios_item):
            _acumular_dia(stats, conv, usuario, cliente)

    linhas = []
    totais_conv = defaultdict(lambda: {'quantidade': 0, 'clientes': set()})
    totais_usuario = defaultdict(lambda: {'quantidade': 0, 'clientes': set()})
    total_q = 0
    total_clientes: set[str] = set()

    for (conv, usuario), dados in sorted(stats.items(), key=lambda x: (x[0][0].lower(), x[0][1].lower())):
        linhas.append({
            'convenio': conv,
            'usuario': usuario,
            'quantidade': dados['quantidade'],
            'quantidade_clientes': len(dados['clientes']),
        })
        totais_conv[conv]['quantidade'] += dados['quantidade']
        totais_conv[conv]['clientes'] |= dados['clientes']
        totais_usuario[usuario]['quantidade'] += dados['quantidade']
        totais_usuario[usuario]['clientes'] |= dados['clientes']
        total_q += dados['quantidade']
        total_clientes |= dados['clientes']

    resumo_convenios = [
        {
            'convenio': conv,
            'quantidade': d['quantidade'],
            'quantidade_clientes': len(d['clientes']),
        }
        for conv, d in sorted(totais_conv.items(), key=lambda x: (-x[1]['quantidade'], x[0].lower()))
    ]
    resumo_usuarios = [
        {
            'usuario': usuario,
            'quantidade': d['quantidade'],
            'quantidade_clientes': len(d['clientes']),
        }
        for usuario, d in sorted(totais_usuario.items(), key=lambda x: (-x[1]['quantidade'], x[0].lower()))
    ]

    regua = montar_resumo_regua_mes(empresa_id, ano, mes, convenios=convenios_sel)
    max_q = max((d['quantidade'] for d in regua), default=0)

    return {
        'dia': dia,
        'dia_ref': dia_ref.isoformat(),
        'dia_label': f'{dia:02d}/{mes:02d}/{ano}',
        'mes_label': f'{MESES_PT[mes]} / {ano}',
        'convenios_selecionados': convenios_sel,
        'linhas': linhas,
        'resumo_convenios': resumo_convenios,
        'resumo_usuarios': resumo_usuarios,
        'total_quantidade': total_q,
        'total_clientes': len(total_clientes),
        'regua_dias': regua,
        'regua_max_quantidade': max_q,
    }
