from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.formats import number_format
from django.http import HttpResponse, Http404, JsonResponse
from django.urls import reverse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from io import BytesIO
from decimal import Decimal, InvalidOperation
import uuid
import logging
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, date, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlencode
from .models import (
    FaturamentoMedico, DocumentoAnexado, ItemServico, ServicoDisponivel, Lote,
    ExtratoPagamentoConvenio,
)
from servicos_medicos.models import Convenio
from empresa.models import Empresa
from .forms import FaturamentoMedicoForm, DocumentoAnexadoForm, ItemServicoForm, ItemServicoFormSet, ServicoDisponivelForm
from .utils import processar_arquivos_com_gemini, processar_arquivos_com_ocr

logger = logging.getLogger(__name__)


def _moeda_br(valor):
    """Formata valor no padrão brasileiro com milhar: 2.100,00"""
    try:
        return number_format(valor or 0, decimal_pos=2, force_grouping=True, use_l10n=True)
    except (TypeError, ValueError):
        return '0,00'

# Status de agendamento fora da lista principal de faturamento
STATUS_AGENDAMENTO_CANCELADOS = (
    'Cancelado',
    'Desistência',
    'Desistencia',
    'Deletado',
    'Deleção',
    'Delecao',
)


def _q_status_agendamento_cancelados():
    q = Q()
    for status in STATUS_AGENDAMENTO_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _filtros_listagem_faturamento(request, use_session_fallback=False):
    """Lê filtros da listagem (GET, com defaults de data iguais à tela)."""
    g = request.GET
    sess = request.session.get('faturamento_filters') or {} if use_session_fallback else {}

    def pick(key, default=''):
        v = g.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
        if use_session_fallback:
            sv = sess.get(key)
            if sv is not None and str(sv).strip():
                return str(sv).strip()
        return default

    convenios = [c.strip() for c in g.getlist('convenio') if c and str(c).strip()]
    if not convenios and use_session_fallback:
        convenios = [c for c in (sess.get('convenio') or []) if c and str(c).strip()]

    hoje = date.today()
    data_inicio = pick('data_inicio')
    data_fim = pick('data_fim')
    if not data_inicio:
        data_inicio = hoje.replace(day=1).strftime('%Y-%m-%d')
    if not data_fim:
        proximo_mes = hoje.replace(day=28) + timedelta(days=4)
        data_fim = (proximo_mes - timedelta(days=proximo_mes.day)).strftime('%Y-%m-%d')

    return {
        'nome': pick('nome'),
        'guia': pick('guia'),
        'anestesista': pick('anestesista'),
        'status': pick('status'),
        'status_conferencia': pick('status_conferencia'),
        'lote': pick('lote'),
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'convenios': convenios,
        'codigo_relatorio': pick('codigo_relatorio'),
    }


def _query_export_faturamento(filtros):
    """Monta query string do export Excel a partir dos filtros efetivos da listagem."""
    params = []
    for key in (
        'nome', 'guia', 'anestesista', 'status', 'status_conferencia', 'lote',
        'data_inicio', 'data_fim', 'codigo_relatorio',
    ):
        val = filtros.get(key)
        if val:
            params.append((key, val))
    for conv in filtros.get('convenios') or []:
        params.append(('convenio', conv))
    return urlencode(params)


def _aplicar_filtros_faturamento_qs(qs, filtros):
    """Aplica os mesmos filtros da listagem ao queryset de faturamentos."""
    nome = filtros.get('nome') or ''
    guia = filtros.get('guia') or ''
    anestesista = filtros.get('anestesista') or ''
    status = filtros.get('status') or ''
    status_conferencia = filtros.get('status_conferencia') or ''
    lote = filtros.get('lote') or ''
    data_inicio = filtros.get('data_inicio') or ''
    data_fim = filtros.get('data_fim') or ''
    convenios = filtros.get('convenios') or []
    codigo_relatorio = filtros.get('codigo_relatorio') or ''

    if nome:
        qs = qs.filter(Q(nome__icontains=nome))
    if guia:
        qs = qs.filter(guia__icontains=guia)
    if codigo_relatorio:
        qs = qs.filter(codigo_relatorio__icontains=codigo_relatorio)
    if anestesista:
        qs = qs.filter(anestesista__icontains=anestesista)
    if status:
        qs = qs.filter(status=status)
    if data_inicio:
        qs = qs.filter(data__gte=data_inicio)
    if data_fim:
        qs = qs.filter(data__lte=data_fim)
    if convenios:
        q_objects = Q()
        for conv in convenios:
            if conv:
                q_objects |= Q(convenio__icontains=conv)
        qs = qs.filter(q_objects)
    if lote == '__sem__':
        qs = qs.filter(Q(lote__isnull=True) | Q(lote=''))
    elif lote:
        qs = qs.filter(lote=lote)

    qs = qs.exclude(_q_status_agendamento_cancelados())

    if status_conferencia:
        if status_conferencia == 'CONFERIDO':
            qs = qs.filter(
                Q(itens_servico__status_conferencia='CONFERIDO')
                | Q(itens_servico__conferido=True)
            ).distinct()
        else:
            qs = qs.filter(
                itens_servico__status_conferencia=status_conferencia,
                itens_servico__conferido=False,
            ).distinct()
    return qs


def _status_linha_faturamento(faturamento, item=None):
    if item is not None:
        return item.status_conferencia_badge()
    if not (faturamento.guia or '').strip():
        return 'FALTA DE GUIA', 'warning'
    if not faturamento.total:
        return 'FALTA DE VALOR NA TABELA', 'danger'
    return 'PENDENTE', 'secondary'


def _eh_status_agendamento_cancelado(status):
    if not status:
        return False
    normalizado = (
        str(status)
        .strip()
        .lower()
        .replace('ê', 'e')
        .replace('é', 'e')
        .replace('ç', 'c')
        .replace('ã', 'a')
    )
    return normalizado in {'cancelado', 'desistencia', 'deletado', 'delecao'}


def _parse_hora_minutos(valor):
    """Converte 'HH:MM' / 'H:MM' em minutos desde 00:00. Retorna None se inválido."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    # Aceita "07:30 - 07:45" pegando só o primeiro horário
    if ' - ' in texto:
        texto = texto.split(' - ', 1)[0].strip()
    texto = texto.replace('.', ':')
    partes = texto.split(':')
    if len(partes) < 2:
        return None
    try:
        hora = int(partes[0])
        minuto = int(partes[1][:2])
    except (TypeError, ValueError):
        return None
    if hora < 0 or hora > 23 or minuto < 0 or minuto > 59:
        return None
    return hora * 60 + minuto


def _intervalos_sobrepoem(ini_a, fim_a, ini_b, fim_b):
    if None in (ini_a, fim_a, ini_b, fim_b):
        return False
    if fim_a <= ini_a:
        fim_a = ini_a + 1
    if fim_b <= ini_b:
        fim_b = ini_b + 1
    return ini_a < fim_b and ini_b < fim_a


def _horario_slot(faturamento):
    ini = _parse_hora_minutos(faturamento.horario_inicio)
    fim = _parse_hora_minutos(faturamento.horario_fim)
    if ini is None and faturamento.horario:
        partes = str(faturamento.horario).split(' - ')
        if len(partes) >= 2:
            ini = _parse_hora_minutos(partes[0])
            fim = _parse_hora_minutos(partes[1])
        else:
            ini = _parse_hora_minutos(faturamento.horario)
    return ini, fim


# Modalidade → (chave da máquina, nome exibido)
# CR (RIS) e RX representam a mesma máquina de Raio X
MAQUINAS_POR_MODALIDADE = {
    'US': ('US', 'Máquina de Ultrassom'),
    'EG': ('EG', 'Máquina de Eletroencefalograma'),
    'MR': ('MR', 'Máquina de Ressonância'),
    'CT': ('CT', 'Máquina de Tomografia'),
    'RX': ('RX', 'Máquina de Raio X'),
    'CR': ('RX', 'Máquina de Raio X'),
    'MG': ('MG', 'Máquina de Mamografia'),
}


def _maquina_por_modalidade(modalidade):
    """Retorna (chave_maquina, nome_maquina) a partir do código de modalidade."""
    cod = (modalidade or '').strip().upper()
    if not cod or cod == '-':
        return None, 'Modalidade não informada'
    if cod in MAQUINAS_POR_MODALIDADE:
        return MAQUINAS_POR_MODALIDADE[cod]
    return cod, f'Máquina {cod}'


def _chaves_maquina_do_faturamento(faturamento):
    """Conjunto de chaves de máquina presentes nos itens do faturamento."""
    chaves = set()
    for item in faturamento.itens_servico.all():
        chave, _ = _maquina_por_modalidade(item.modalidade)
        if chave:
            chaves.add(chave)
    return chaves


def _analisar_vaga_maquina(faturamento, modalidade, candidatos_ativos):
    """
    Verifica se o horário cancelado foi reutilizado na MESMA máquina (modalidade).
    US/EG/MR/CT/RX(CR)/MG.
    """
    ini, fim = _horario_slot(faturamento)
    local = (faturamento.local or '').strip().upper()
    chave_maquina, nome_maquina = _maquina_por_modalidade(modalidade)

    if not chave_maquina:
        return {
            'situacao': 'SEM_MODALIDADE',
            'situacao_css': 'secondary',
            'situacao_label': 'Sem modalidade',
            'maquina': nome_maquina,
            'maquina_codigo': '-',
            'reutilizado_por': '-',
            'reutilizacoes': [],
        }

    reutilizacoes = []

    for outro in candidatos_ativos:
        if outro.id == faturamento.id:
            continue
        if outro.data != faturamento.data:
            continue
        outro_local = (outro.local or '').strip().upper()
        if local and outro_local and local != outro_local:
            continue

        # Obrigatório: mesma máquina (modalidade)
        chaves_outro = _chaves_maquina_do_faturamento(outro)
        if chave_maquina not in chaves_outro:
            continue

        ini_o, fim_o = _horario_slot(outro)
        sobrepoe = _intervalos_sobrepoem(ini, fim, ini_o, fim_o)
        if not sobrepoe:
            h1 = (faturamento.horario or '').strip()
            h2 = (outro.horario or '').strip()
            if not h1 or not h2 or h1 != h2:
                continue

        procs = []
        mods_usadas = []
        for it in outro.itens_servico.all():
            chave_it, _ = _maquina_por_modalidade(it.modalidade)
            if chave_it == chave_maquina:
                if (it.servico or '').strip():
                    procs.append((it.servico or '').strip())
                if (it.modalidade or '').strip():
                    mods_usadas.append((it.modalidade or '').strip().upper())
        if not procs:
            procs = [(outro.servico or '-')]

        horario_txt = ''
        if outro.horario_inicio or outro.horario_fim:
            horario_txt = f"{outro.horario_inicio or ''} - {outro.horario_fim or ''}".strip(' -')
        else:
            horario_txt = (outro.horario or '').strip()

        reutilizacoes.append({
            'id': outro.id,
            'faturamento': outro,
            'paciente': outro.nome or '-',
            'status': outro.status_agendamento or '-',
            'horario': horario_txt or '-',
            'data': outro.data,
            'local': outro.local or '-',
            'convenio': outro.convenio or '-',
            'agendado_via': outro.agendado_via or '-',
            'procedimentos': ', '.join(procs),
            'modalidade': ', '.join(dict.fromkeys(mods_usadas)) or (modalidade or '-'),
            'maquina': nome_maquina,
        })

    base = {
        'maquina': nome_maquina,
        'maquina_codigo': chave_maquina,
    }

    if reutilizacoes:
        nomes = ', '.join(
            f"{r['paciente']} ({r['status']})" for r in reutilizacoes[:3]
        )
        if len(reutilizacoes) > 3:
            nomes += f' +{len(reutilizacoes) - 3}'
        return {
            **base,
            'situacao': 'REUTILIZADA',
            'situacao_css': 'success',
            'situacao_label': 'Horário reutilizado',
            'reutilizado_por': nomes,
            'reutilizacoes': reutilizacoes,
        }

    return {
        **base,
        'situacao': 'MAQUINA_VAGA',
        'situacao_css': 'warning',
        'situacao_label': 'Máquina vaga',
        'reutilizado_por': '-',
        'reutilizacoes': [],
    }


def listar_faturamentos(request):
    """Lista todos os faturamentos médicos com filtros"""
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        faturamentos = FaturamentoMedico.objects.filter(empresa_id=empresa_id).order_by('-data')
    else:
        faturamentos = FaturamentoMedico.objects.all().order_by('-data')

    filtros = _filtros_listagem_faturamento(request)
    faturamentos = _aplicar_filtros_faturamento_qs(faturamentos, filtros)
    nome = filtros['nome']
    guia = filtros['guia']
    anestesista = filtros['anestesista']
    status = filtros['status']
    status_conferencia = filtros['status_conferencia']
    lote = filtros['lote']
    data_inicio = filtros['data_inicio']
    data_fim = filtros['data_fim']
    convenios = filtros['convenios']
    codigo_relatorio = filtros['codigo_relatorio']

    # Estatísticas
    total_faturamentos = faturamentos.count()
    valor_total = sum(f.total for f in faturamentos if f.total)

    # Estatísticas por convênio
    from django.db.models import Sum, Count
    stats_convenio = list(faturamentos.values('convenio').annotate(
        total_valor=Sum('total'),
        quantidade=Count('id')
    ).order_by('-total_valor'))
    for stat in stats_convenio:
        stat['total_valor_fmt'] = _moeda_br(stat.get('total_valor') or 0)

    def _label_convenio_curto(nome, max_len=36):
        n = (nome or '').strip() or 'Não informado'
        if len(n) <= max_len:
            return n
        return n[: max_len - 1].rstrip() + '…'

    grafico_convenio_labels = [_label_convenio_curto(s.get('convenio')) for s in stats_convenio]
    grafico_convenio_keys = [(s.get('convenio') or '').strip() or 'Não informado' for s in stats_convenio]
    grafico_convenio_valores = [float(s.get('total_valor') or 0) for s in stats_convenio]
    grafico_convenio_qtde = [int(s.get('quantidade') or 0) for s in stats_convenio]

    # Estatísticas por anestesista
    stats_anestesista = list(faturamentos.values('anestesista').annotate(
        total_valor=Sum('total'),
        quantidade=Count('id')
    ).exclude(anestesista__isnull=True).exclude(anestesista='').order_by('-total_valor'))
    for stat in stats_anestesista:
        stat['total_valor_fmt'] = _moeda_br(stat.get('total_valor') or 0)

    # Buscar convênios disponíveis para a empresa
    convenios_disponiveis = []
    if empresa_id:
        from servicos_medicos.models import Convenio
        convenios_disponiveis = list(Convenio.objects.filter(empresa_id=empresa_id).order_by('nome'))
        if not convenios_disponiveis:
            # Convênios padrão se nenhum for encontrado para a empresa
            convenios_padrao = [
                {'nome': 'CBSAUDE'},
                {'nome': 'PM'},
                {'nome': 'UNIMED'},
                {'nome': 'BRADESCO'},
                {'nome': 'GEAP'},
                {'nome': 'SAUDE CAIXA'},
                {'nome': 'POSTAL SAUDE'},
                {'nome': 'FUSEX'},
                {'nome': 'LIFE EMPRESARIAL'},
                {'nome': 'CASSI'},
                {'nome': 'GCARD'},
                {'nome': 'PERSONAL NET'},
            ]
            convenios_disponiveis = convenios_padrao

    # Buscar lotes disponíveis para a empresa
    lotes_disponiveis = []
    lotes_filtro = []
    if empresa_id:
        lotes_disponiveis = Lote.objects.filter(empresa_id=empresa_id).order_by('-id')
        lotes_filtro = list(lotes_disponiveis)
        # Inclui valores de lote vindos da importação RIS (texto livre)
        ids_lote = {str(l.id) for l in lotes_filtro}
        lotes_extras = (
            FaturamentoMedico.objects
            .filter(empresa_id=empresa_id)
            .exclude(Q(lote__isnull=True) | Q(lote=''))
            .values_list('lote', flat=True)
            .distinct()
        )
        for valor in lotes_extras:
            if valor and str(valor) not in ids_lote:
                lotes_filtro.append(type('LoteExtra', (), {
                    'id': valor,
                    'convenio': 'RIS/Outro',
                    'total_lote': None,
                })())

    # Grid pós-filtragem (modelo RIS): uma linha por procedimento
    faturamentos = faturamentos.prefetch_related('itens_servico')
    grid_linhas = []

    # Cache de preços da tabela por empresa/convênio (código e descrição)
    precos_por_codigo = set()
    precos_por_descricao = set()
    if empresa_id:
        from servicos_medicos.models import TabelaPreco
        tabelas = (
            TabelaPreco.objects
            .filter(empresa_id=empresa_id)
            .select_related('codigo_servico', 'convenio')
        )
        for t in tabelas:
            conv = (t.convenio.nome or '').strip().upper()
            cod = (t.codigo_servico.codigo or '').strip().upper()
            desc = (t.codigo_servico.servicos or '').strip().upper()
            if conv and cod:
                precos_por_codigo.add((conv, cod))
            if conv and desc:
                precos_por_descricao.add((conv, desc))

    def _tem_preco_tabela(faturamento, item):
        if not item:
            return False
        valor = item.total if item.total is not None else item.valor
        if valor is None or valor == 0:
            return False
        conv = (faturamento.convenio or '').strip().upper()
        if not conv:
            return False
        cod = (item.codigo_servico or '').strip().upper()
        if cod and (conv, cod) in precos_por_codigo:
            return True
        desc = (item.servico or '').strip().upper()
        if desc and (conv, desc) in precos_por_descricao:
            return True
        # Sem código/descrição na tabela do convênio
        if not precos_por_codigo and not precos_por_descricao:
            # Sem tabela cadastrada: considera falta de preço
            return False
        return False

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

    for faturamento in faturamentos:
        itens = list(faturamento.itens_servico.all())
        if not itens:
            status_label, status_css = _status_linha_faturamento(faturamento)
            if status_conferencia and status_label != status_conferencia:
                continue
            grid_linhas.append({
                'faturamento': faturamento,
                'item': None,
                'paciente': faturamento.nome or '-',
                'nome_associado': faturamento.nome_associado or faturamento.nome or '-',
                'procedimento': faturamento.servico or '-',
                'modalidade': _modalidade_item(faturamento),
                'com_contraste': 'contraste' in (faturamento.servico or '').lower(),
                'valor': faturamento.total or 0,
                'valor_fmt': _moeda_br(faturamento.total or 0),
                'conferido': False,
                'status_conferencia': status_label,
                'status_conferencia_css': status_css,
                'mostrar_selecao_lote': True,
            })
            continue
        itens_filtrados = []
        for item in itens:
            status_label, status_css = _status_linha_faturamento(faturamento, item)
            if status_conferencia and status_label != status_conferencia:
                continue
            itens_filtrados.append((item, status_label, status_css))
        for idx, (item, status_label, status_css) in enumerate(itens_filtrados):
            valor_item = item.total if item.total is not None else (item.valor or 0)
            grid_linhas.append({
                'faturamento': faturamento,
                'item': item,
                'paciente': faturamento.nome or '-',
                'nome_associado': faturamento.nome_associado or faturamento.nome or '-',
                'procedimento': item.servico or '-',
                'modalidade': _modalidade_item(faturamento, item),
                'com_contraste': item.com_contraste,
                'valor': valor_item,
                'valor_fmt': _moeda_br(valor_item),
                'conferido': item.conferido,
                'status_conferencia': status_label,
                'status_conferencia_css': status_css,
                'mostrar_selecao_lote': idx == 0,
            })

    # Resumo por modalidade (conforme filtros / grid de procedimentos)
    MODALIDADES_RESUMO = [
        ('US', 'QUANTIDADE DE ULTRASSONOGRAFIA'),
        ('CT', 'QUANTIDADE DE TOMOGRAFIA'),
        ('MG', 'QUANTIDADE DE MAMOGRAFIA'),
        ('CR', 'QUANTIDADE DE RAIO X'),
        ('MR', 'QUANTIDADE DE RESSONÂNCIA'),
        ('EG', 'QUANTIDADE DE ELETROENCEFALOGRAMA'),
        ('EC', 'QUANTIDADE DE ELETROCARDIOGRAMA'),
    ]
    contagem_modalidade = {codigo: 0 for codigo, _ in MODALIDADES_RESUMO}
    resumo_quantidade_total = 0
    resumo_valor_total = Decimal('0')
    for linha in grid_linhas:
        resumo_quantidade_total += 1
        try:
            resumo_valor_total += Decimal(str(linha.get('valor') or 0))
        except (InvalidOperation, ValueError, TypeError):
            pass
        codigo_mod = (linha.get('modalidade') or '').strip().upper()
        # CR e RX contam juntos como Raio X
        if codigo_mod == 'RX':
            codigo_mod = 'CR'
        if codigo_mod in contagem_modalidade:
            contagem_modalidade[codigo_mod] += 1

    resumo_modalidades = [
        {
            'codigo': codigo,
            'label': label,
            'quantidade': contagem_modalidade[codigo],
        }
        for codigo, label in MODALIDADES_RESUMO
    ]

    MODALIDADES_LABEL_CURTO = {
        'US': 'Ultrassonografia',
        'CT': 'Tomografia',
        'MG': 'Mamografia',
        'CR': 'Raio X',
        'MR': 'Ressonância',
        'EG': 'EEG',
        'EC': 'ECG',
    }
    grafico_modalidade_labels = [
        MODALIDADES_LABEL_CURTO.get(m['codigo'], m['codigo']) for m in resumo_modalidades
    ]
    grafico_modalidade_valores = [m['quantidade'] for m in resumo_modalidades]

    # Gráfico por procedimento (top 8 + Outros)
    contagem_procedimento = defaultdict(int)
    for linha in grid_linhas:
        nome_proc = (linha.get('procedimento') or '').strip() or 'Não informado'
        contagem_procedimento[nome_proc] += 1
    procedimentos_ordenados = sorted(
        contagem_procedimento.items(), key=lambda x: (-x[1], x[0].lower())
    )
    TOP_PROCEDIMENTOS = 8

    def _label_proc_curto(nome, max_len=42):
        n = (nome or '').strip()
        if len(n) <= max_len:
            return n
        return n[: max_len - 1].rstrip() + '…'

    if len(procedimentos_ordenados) <= TOP_PROCEDIMENTOS:
        grafico_procedimento_labels = [_label_proc_curto(n) for n, _ in procedimentos_ordenados]
        grafico_procedimento_valores = [q for _, q in procedimentos_ordenados]
    else:
        top = procedimentos_ordenados[:TOP_PROCEDIMENTOS]
        resto = sum(q for _, q in procedimentos_ordenados[TOP_PROCEDIMENTOS:])
        grafico_procedimento_labels = [_label_proc_curto(n) for n, _ in top] + ['Outros']
        grafico_procedimento_valores = [q for _, q in top] + [resto]

    # Detalhe por convênio (modalidade + procedimento) para drill-down nos gráficos
    MOD_CODIGO_LABEL = dict(MODALIDADES_LABEL_CURTO)
    por_convenio_mod = defaultdict(lambda: defaultdict(int))
    por_convenio_proc = defaultdict(lambda: defaultdict(int))
    for linha in grid_linhas:
        fat = linha.get('faturamento')
        conv = ((getattr(fat, 'convenio', None) if fat else None) or '').strip() or 'Não informado'
        codigo_mod = (linha.get('modalidade') or '').strip().upper()
        if codigo_mod == 'RX':
            codigo_mod = 'CR'
        label_mod = MOD_CODIGO_LABEL.get(codigo_mod, codigo_mod if codigo_mod and codigo_mod != '-' else 'Outros')
        por_convenio_mod[conv][label_mod] += 1
        nome_proc = (linha.get('procedimento') or '').strip() or 'Não informado'
        por_convenio_proc[conv][nome_proc] += 1

    detalhe_convenio = {}
    for conv in set(list(por_convenio_mod.keys()) + list(por_convenio_proc.keys())):
        mods = sorted(por_convenio_mod[conv].items(), key=lambda x: (-x[1], x[0]))
        procs = sorted(por_convenio_proc[conv].items(), key=lambda x: (-x[1], x[0].lower()))
        if len(procs) > TOP_PROCEDIMENTOS:
            top_p = procs[:TOP_PROCEDIMENTOS]
            resto_p = sum(q for _, q in procs[TOP_PROCEDIMENTOS:])
            proc_labels = [_label_proc_curto(n) for n, _ in top_p] + ['Outros']
            proc_vals = [q for _, q in top_p] + [resto_p]
        else:
            proc_labels = [_label_proc_curto(n) for n, _ in procs]
            proc_vals = [q for _, q in procs]
        detalhe_convenio[conv] = {
            'modalidade': {
                'labels': [n for n, _ in mods],
                'valores': [q for _, q in mods],
            },
            'procedimento': {
                'labels': proc_labels,
                'valores': proc_vals,
            },
        }

    # Paginação da tabela (resumo/gráficos usam a lista completa)
    PER_PAGE_OPCOES = (25, 100, 250, 500, 1000)
    try:
        per_page = int(request.GET.get('per_page') or 25)
    except (TypeError, ValueError):
        per_page = 25
    if per_page not in PER_PAGE_OPCOES:
        per_page = 25
    grid_total = len(grid_linhas)
    paginator = Paginator(grid_linhas, per_page)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    grid_linhas = list(page_obj.object_list)

    # Armazenar filtros na sessão para preservar ao voltar de edição
    request.session['faturamento_filters'] = {
        'nome': nome or '',
        'guia': guia or '',
        'anestesista': anestesista or '',
        'status': status or '',
        'status_conferencia': status_conferencia or '',
        'lote': lote or '',
        'data_inicio': data_inicio or '',
        'data_fim': data_fim or '',
        'convenio': convenios or [],
        'codigo_relatorio': codigo_relatorio or '',
        'per_page': str(per_page),
    }

    context = {
        'faturamentos': faturamentos,
        'grid_linhas': grid_linhas,
        'grid_total': grid_total,
        'page_obj': page_obj,
        'per_page': per_page,
        'per_page_opcoes': PER_PAGE_OPCOES,
        'total_faturamentos': total_faturamentos,
        'valor_total': valor_total,
        'valor_total_fmt': _moeda_br(valor_total),
        'resumo_modalidades': resumo_modalidades,
        'resumo_quantidade_total': resumo_quantidade_total,
        'resumo_valor_total': resumo_valor_total,
        'resumo_valor_total_fmt': _moeda_br(resumo_valor_total),
        'grafico_modalidade_labels': json.dumps(grafico_modalidade_labels, ensure_ascii=False),
        'grafico_modalidade_valores': json.dumps(grafico_modalidade_valores),
        'grafico_procedimento_labels': json.dumps(grafico_procedimento_labels, ensure_ascii=False),
        'grafico_procedimento_valores': json.dumps(grafico_procedimento_valores),
        'grafico_convenio_labels': json.dumps(grafico_convenio_labels, ensure_ascii=False),
        'grafico_convenio_keys': json.dumps(grafico_convenio_keys, ensure_ascii=False),
        'grafico_convenio_valores': json.dumps(grafico_convenio_valores),
        'grafico_convenio_qtde': json.dumps(grafico_convenio_qtde),
        'detalhe_convenio': json.dumps(detalhe_convenio, ensure_ascii=False),
        'status_conferencia_choices': ItemServico.STATUS_CONFERENCIA_CHOICES,
        'stats_convenio': stats_convenio,
        'stats_anestesista': stats_anestesista,
        'convenios_disponiveis': convenios_disponiveis,
        'lotes_disponiveis': lotes_disponiveis,
        'lotes_filtro': lotes_filtro,
        'filtros': {
            'nome': nome,
            'guia': guia,
            'anestesista': anestesista,
            'status': status,
            'status_conferencia': status_conferencia,
            'lote': lote,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'convenio': convenios,
            'codigo_relatorio': codigo_relatorio,
            'per_page': str(per_page),
        },
        'export_query_string': _query_export_faturamento(filtros),
    }

    return render(request, 'faturamento_medico/listar.html', context)


def listar_cancelados(request):
    """Lista procedimentos com status Cancelado, Desistência ou Deletado."""
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        faturamentos = FaturamentoMedico.objects.filter(empresa_id=empresa_id).order_by('-data', 'nome')
    else:
        faturamentos = FaturamentoMedico.objects.all().order_by('-data', 'nome')

    faturamentos = faturamentos.filter(_q_status_agendamento_cancelados())

    nome = request.GET.get('nome')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    convenios = request.GET.getlist('convenio')
    status_agendamento = request.GET.get('status_agendamento')
    situacao_vaga = (request.GET.get('situacao_vaga') or '').strip()
    maquina = (request.GET.get('maquina') or '').strip().upper()

    hoje = date.today()
    if not data_inicio:
        data_inicio = hoje.replace(day=1).strftime('%Y-%m-%d')
    if not data_fim:
        proximo_mes = hoje.replace(day=28) + timedelta(days=4)
        data_fim = (proximo_mes - timedelta(days=proximo_mes.day)).strftime('%Y-%m-%d')

    if nome:
        faturamentos = faturamentos.filter(Q(nome__icontains=nome))
    if data_inicio:
        faturamentos = faturamentos.filter(data__gte=data_inicio)
    if data_fim:
        faturamentos = faturamentos.filter(data__lte=data_fim)
    if convenios:
        q_objects = Q()
        for conv in convenios:
            if conv:
                q_objects |= Q(convenio__icontains=conv)
        faturamentos = faturamentos.filter(q_objects)
    if status_agendamento:
        faturamentos = faturamentos.filter(status_agendamento__iexact=status_agendamento)

    faturamentos = list(faturamentos.prefetch_related('itens_servico'))

    # Candidatos ativos no mesmo período (outros status) para checar reuso do horário
    datas = {f.data for f in faturamentos if f.data}
    ativos_qs = FaturamentoMedico.objects.none()
    if datas:
        ativos_qs = (
            FaturamentoMedico.objects
            .filter(data__in=datas)
            .exclude(_q_status_agendamento_cancelados())
            .prefetch_related('itens_servico')
        )
        if empresa_id:
            ativos_qs = ativos_qs.filter(empresa_id=empresa_id)
    ativos_por_data = {}
    for ativo in ativos_qs:
        ativos_por_data.setdefault(ativo.data, []).append(ativo)

    grid_linhas = []
    total_vagas = 0
    total_reutilizadas = 0
    for faturamento in faturamentos:
        candidatos = ativos_por_data.get(faturamento.data, [])
        itens = list(faturamento.itens_servico.all())
        if not itens:
            analise = _analisar_vaga_maquina(faturamento, '-', candidatos)
            if situacao_vaga and analise['situacao'] != situacao_vaga:
                continue
            if maquina and (analise.get('maquina_codigo') or '') != maquina:
                continue
            if analise['situacao'] == 'MAQUINA_VAGA':
                total_vagas += 1
            elif analise['situacao'] == 'REUTILIZADA':
                total_reutilizadas += 1
            grid_linhas.append({
                'faturamento': faturamento,
                'procedimento': faturamento.servico or '-',
                'modalidade': '-',
                'valor': faturamento.total or 0,
                'valor_fmt': _moeda_br(faturamento.total or 0),
                **analise,
            })
            continue
        for item in itens:
            modalidade = item.modalidade or '-'
            analise = _analisar_vaga_maquina(faturamento, modalidade, candidatos)
            if situacao_vaga and analise['situacao'] != situacao_vaga:
                continue
            if maquina and (analise.get('maquina_codigo') or '') != maquina:
                continue
            if analise['situacao'] == 'MAQUINA_VAGA':
                total_vagas += 1
            elif analise['situacao'] == 'REUTILIZADA':
                total_reutilizadas += 1
            valor_item = item.total if item.total is not None else (item.valor or 0)
            grid_linhas.append({
                'faturamento': faturamento,
                'procedimento': item.servico or '-',
                'modalidade': modalidade,
                'valor': valor_item,
                'valor_fmt': _moeda_br(valor_item),
                **analise,
            })

    convenios_disponiveis = []
    if empresa_id:
        from servicos_medicos.models import Convenio
        convenios_disponiveis = list(Convenio.objects.filter(empresa_id=empresa_id).order_by('nome'))

    # Opções únicas de máquina para o filtro (chave → nome)
    maquinas_opcoes = []
    vistos = set()
    for chave, nome in MAQUINAS_POR_MODALIDADE.values():
        if chave not in vistos:
            vistos.add(chave)
            maquinas_opcoes.append({'codigo': chave, 'nome': nome})

    context = {
        'grid_linhas': grid_linhas,
        'total_procedimentos': len(grid_linhas),
        'total_maquina_vaga': total_vagas,
        'total_reutilizadas': total_reutilizadas,
        'valor_total': sum((linha['valor'] or 0) for linha in grid_linhas),
        'valor_total_fmt': _moeda_br(sum((linha['valor'] or 0) for linha in grid_linhas)),
        'convenios_disponiveis': convenios_disponiveis,
        'status_opcoes': ['Cancelado', 'Desistência', 'Deletado'],
        'maquinas_opcoes': maquinas_opcoes,
        'filtros': {
            'nome': nome,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'convenio': convenios,
            'status_agendamento': status_agendamento or '',
            'situacao_vaga': situacao_vaga,
            'maquina': maquina,
        },
    }
    return render(request, 'faturamento_medico/listar_cancelados.html', context)


FUZZY_NOME_MIN_RATIO = 0.90


def _normalizar_nome_servico(texto):
    """Uppercase, sem acentos e espaços extras — para comparar nomes de procedimento."""
    if not texto:
        return ''
    t = unicodedata.normalize('NFKD', str(texto))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'\s+', ' ', t.upper().strip())
    return t


def _nome_base_procedimento(texto):
    """Remove complemento entre parênteses (descrição longa no faturamento)."""
    base = _normalizar_nome_servico(texto)
    if '(' in base:
        base = base.split('(', 1)[0].strip()
    return base


def _similaridade_nome_procedimento(a, b):
    """
    Similaridade 0–1 entre dois nomes de procedimento.
    Compara texto completo e nome base (antes de parênteses).
    """
    candidatos_a = {_normalizar_nome_servico(a), _nome_base_procedimento(a)}
    candidatos_b = {_normalizar_nome_servico(b), _nome_base_procedimento(b)}
    candidatos_a.discard('')
    candidatos_b.discard('')
    if not candidatos_a or not candidatos_b:
        return 0.0
    melhor = 0.0
    for na in candidatos_a:
        for nb in candidatos_b:
            if na == nb:
                return 1.0
            melhor = max(melhor, SequenceMatcher(None, na, nb).ratio())
    return melhor


def _pool_precos_convenio(empresa_id, convenio_nome):
    """Carrega tabela de preços do convênio uma vez (lookup por código/nome)."""
    from servicos_medicos.models import TabelaPreco, Convenio

    conv_key = (convenio_nome or '').strip().upper()
    pool = {
        'tabelas': [],
        'por_codigo': {},
        'por_nome': {},
        'por_base': {},
    }
    if not empresa_id or not conv_key:
        return pool

    convenios = list(
        Convenio.objects.filter(empresa_id=empresa_id).filter(
            Q(nome__iexact=convenio_nome) | Q(nome__icontains=convenio_nome)
        )
    )
    if not convenios:
        convenios = [
            c for c in Convenio.objects.filter(empresa_id=empresa_id)
            if c.nome and c.nome.upper() in conv_key
        ]
    if not convenios:
        return pool

    tabelas = list(
        TabelaPreco.objects.filter(
            empresa_id=empresa_id,
            convenio__in=convenios,
        ).select_related('codigo_servico')
    )
    pool['tabelas'] = tabelas
    for tabela in tabelas:
        cod = (tabela.codigo_servico.codigo or '').strip().upper()
        if cod:
            pool['por_codigo'].setdefault(cod, tabela)
        nome = tabela.codigo_servico.servicos or ''
        nome_norm = _normalizar_nome_servico(nome)
        if nome_norm:
            pool['por_nome'].setdefault(nome_norm, tabela)
        nome_base = _nome_base_procedimento(nome)
        if nome_base:
            pool['por_base'].setdefault(nome_base, tabela)
    return pool


def _get_pool_precos(cache_precos, empresa_id, convenio_nome):
    conv_key = (convenio_nome or '').strip().upper()
    pool_key = ('__pool__', empresa_id, conv_key)
    if pool_key not in cache_precos:
        cache_precos[pool_key] = _pool_precos_convenio(empresa_id, convenio_nome)
    return cache_precos[pool_key]


def _buscar_tabela_por_nome_proximo(pool, descricao, min_ratio=FUZZY_NOME_MIN_RATIO):
    """Melhor TabelaPreco cujo nome do serviço atinge similaridade mínima."""
    if not (descricao or '').strip():
        return None, 0.0

    desc_norm = _normalizar_nome_servico(descricao)
    desc_base = _nome_base_procedimento(descricao)
    if desc_norm in pool['por_nome']:
        return pool['por_nome'][desc_norm], 1.0
    if desc_base in pool['por_base']:
        return pool['por_base'][desc_base], 1.0

    tokens = [t for t in re.split(r'\W+', desc_norm) if len(t) >= 4][:4]
    candidatos = pool['tabelas']
    if tokens:
        filtrados = []
        for tabela in candidatos:
            nome = _normalizar_nome_servico(tabela.codigo_servico.servicos or '')
            if any(tok in nome for tok in tokens):
                filtrados.append(tabela)
        if filtrados:
            candidatos = filtrados[:120]

    melhor_tabela = None
    melhor_ratio = 0.0
    for tabela in candidatos:
        nome = tabela.codigo_servico.servicos or ''
        ratio = _similaridade_nome_procedimento(descricao, nome)
        if ratio > melhor_ratio:
            melhor_ratio = ratio
            melhor_tabela = tabela
    if melhor_tabela is not None and melhor_ratio >= min_ratio:
        return melhor_tabela, melhor_ratio
    return None, melhor_ratio


def _buscar_tabela_por_nome_proximo_qs(qs, descricao, min_ratio=FUZZY_NOME_MIN_RATIO):
    """Compatibilidade: usa pool montado a partir de queryset."""
    pool = {
        'tabelas': list(qs.select_related('codigo_servico')),
        'por_codigo': {},
        'por_nome': {},
        'por_base': {},
    }
    for tabela in pool['tabelas']:
        cod = (tabela.codigo_servico.codigo or '').strip().upper()
        if cod:
            pool['por_codigo'].setdefault(cod, tabela)
        nome = tabela.codigo_servico.servicos or ''
        nome_norm = _normalizar_nome_servico(nome)
        if nome_norm:
            pool['por_nome'].setdefault(nome_norm, tabela)
        nome_base = _nome_base_procedimento(nome)
        if nome_base:
            pool['por_base'].setdefault(nome_base, tabela)
    return _buscar_tabela_por_nome_proximo(pool, descricao, min_ratio)


def _resolver_preco_tabela(empresa_id, convenio_nome, codigo_servico, descricao_servico, tipo_acomodacao, cache_precos):
    """
    Resolve preço da TabelaPreco para um item.
    Retorna (preco Decimal|None, codigo_encontrado, descricao_encontrada).
    """
    from servicos_medicos.models import TabelaPreco

    conv_key = (convenio_nome or '').strip().upper()
    cod = (codigo_servico or '').strip().upper()
    desc = (descricao_servico or '').strip().upper()
    usa_apto = (tipo_acomodacao or '').strip().lower() == 'apartamento'
    cache_key = (conv_key, cod, desc, usa_apto)
    if cache_key in cache_precos:
        return cache_precos[cache_key]

    resultado = (None, '', '')
    if not empresa_id or not conv_key:
        cache_precos[cache_key] = resultado
        return resultado

    pool = _get_pool_precos(cache_precos, empresa_id, convenio_nome)
    if not pool['tabelas']:
        cache_precos[cache_key] = resultado
        return resultado

    tabela = None
    if cod:
        tabela = pool['por_codigo'].get(cod)
    if tabela is None and desc:
        desc_norm = _normalizar_nome_servico(descricao_servico)
        tabela = pool['por_nome'].get(desc_norm) or pool['por_base'].get(_nome_base_procedimento(descricao_servico))
    if tabela is None and desc:
        tabela, _ratio = _buscar_tabela_por_nome_proximo(pool, descricao_servico)

    if tabela is None:
        cache_precos[cache_key] = resultado
        return resultado

    preco = tabela.preco_apartamento if usa_apto else tabela.preco_enfermaria
    resultado = (
        Decimal(str(preco or 0)),
        (tabela.codigo_servico.codigo or ''),
        (tabela.codigo_servico.servicos or ''),
    )
    cache_precos[cache_key] = resultado
    return resultado


def verificar_corrigir_precos(request):
    """
    Filtra procedimentos por período e convênio, compara valor atual x tabela
    e permite aplicar o preço correto nos itens selecionados.
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    try:
        empresa_id = int(empresa_id)
    except (TypeError, ValueError):
        messages.error(request, 'Empresa inválida na sessão.')
        return redirect('faturamento_medico:ftlistar')

    from servicos_medicos.models import Convenio

    convenios_disponiveis = list(
        Convenio.objects.filter(empresa_id=empresa_id).order_by('nome')
    )

    hoje = date.today()
    data_inicio = request.GET.get('data_inicio') or request.POST.get('data_inicio')
    data_fim = request.GET.get('data_fim') or request.POST.get('data_fim')
    convenio = (request.GET.get('convenio') or request.POST.get('convenio') or '').strip()
    procedimento = (request.GET.get('procedimento') or request.POST.get('procedimento') or '').strip()
    so_divergentes = (request.GET.get('so_divergentes') or request.POST.get('so_divergentes') or '') == '1'

    if not data_inicio:
        data_inicio = hoje.replace(day=1).strftime('%Y-%m-%d')
    if not data_fim:
        proximo_mes = hoje.replace(day=28) + timedelta(days=4)
        data_fim = (proximo_mes - timedelta(days=proximo_mes.day)).strftime('%Y-%m-%d')

    # Aplicar preços selecionados
    if request.method == 'POST' and request.POST.get('acao') == 'aplicar':
        ids = request.POST.getlist('itens_selecionados')
        if not ids:
            messages.warning(request, 'Selecione ao menos um procedimento para corrigir.')
        else:
            cache_precos = {}
            corrigidos = 0
            sem_preco = 0
            faturamentos_atualizar = set()
            itens = (
                ItemServico.objects
                .select_related('faturamento')
                .filter(pk__in=ids, faturamento__empresa_id=empresa_id)
            )
            for item in itens:
                fat = item.faturamento
                preco, cod_tab, _desc = _resolver_preco_tabela(
                    empresa_id,
                    fat.convenio,
                    item.codigo_servico,
                    item.servico,
                    fat.apartamento_enfermaria,
                    cache_precos,
                )
                if preco is None:
                    sem_preco += 1
                    continue
                item.valor = preco
                if cod_tab and not (item.codigo_servico or '').strip():
                    item.codigo_servico = cod_tab
                item.save()
                faturamentos_atualizar.add(fat.id)
                corrigidos += 1

            for fat_id in faturamentos_atualizar:
                try:
                    FaturamentoMedico.objects.get(pk=fat_id).atualizar_total()
                except FaturamentoMedico.DoesNotExist:
                    pass

            if corrigidos:
                messages.success(request, f'{corrigidos} procedimento(s) atualizado(s) com o preço da tabela.')
            if sem_preco:
                messages.warning(request, f'{sem_preco} item(ns) sem preço correspondente na tabela.')

        qs = urlencode({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'convenio': convenio,
            'procedimento': procedimento,
            'so_divergentes': '1' if so_divergentes else '',
        })
        return redirect(f"{reverse('faturamento_medico:verificar_corrigir_precos')}?{qs}")

    linhas = []
    resumo = {
        'total': 0,
        'ok': 0,
        'divergente': 0,
        'sem_preco': 0,
        'valor_atual': Decimal('0'),
        'valor_tabela': Decimal('0'),
    }

    if convenio:
        faturamentos = (
            FaturamentoMedico.objects
            .filter(empresa_id=empresa_id)
            .exclude(_q_status_agendamento_cancelados())
            .filter(data__gte=data_inicio, data__lte=data_fim)
            .filter(convenio__icontains=convenio)
            .prefetch_related('itens_servico')
            .order_by('data', 'nome')
        )

        cache_precos = {}
        for fat in faturamentos:
            for item in fat.itens_servico.all():
                if procedimento and procedimento.lower() not in (item.servico or '').lower():
                    continue

                valor_atual = Decimal(str(item.valor or 0))
                preco, cod_tab, desc_tab = _resolver_preco_tabela(
                    empresa_id,
                    fat.convenio,
                    item.codigo_servico,
                    item.servico,
                    fat.apartamento_enfermaria,
                    cache_precos,
                )
                if preco is None:
                    situacao = 'SEM PRECO'
                    css = 'warning'
                    diferenca = None
                    valor_esperado = None
                    pode_corrigir = False
                else:
                    valor_esperado = preco
                    diferenca = valor_atual - preco
                    if abs(diferenca) < Decimal('0.01'):
                        situacao = 'OK'
                        css = 'success'
                        pode_corrigir = False
                    else:
                        situacao = 'DIVERGENTE'
                        css = 'danger'
                        pode_corrigir = True

                if so_divergentes and situacao == 'OK':
                    continue

                if situacao == 'SEM PRECO':
                    resumo['sem_preco'] += 1
                elif situacao == 'OK':
                    resumo['ok'] += 1
                else:
                    resumo['divergente'] += 1

                if valor_esperado is not None:
                    resumo['valor_tabela'] += valor_esperado

                resumo['total'] += 1
                resumo['valor_atual'] += valor_atual
                linhas.append({
                    'item': item,
                    'faturamento': fat,
                    'valor_atual': valor_atual,
                    'valor_esperado': valor_esperado,
                    'diferenca': diferenca,
                    'situacao': situacao,
                    'situacao_css': css,
                    'pode_corrigir': pode_corrigir,
                    'codigo_tabela': cod_tab,
                    'descricao_tabela': desc_tab,
                })

    context = {
        'linhas': linhas,
        'resumo': resumo,
        'convenios_disponiveis': convenios_disponiveis,
        'filtros': {
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'convenio': convenio,
            'procedimento': procedimento,
            'so_divergentes': so_divergentes,
        },
    }
    return render(request, 'faturamento_medico/verificar_corrigir_precos.html', context)


def criar_faturamento(request):
    """Cria um novo faturamento médico"""
    logger.info("Iniciando criar_faturamento")
    empresa_id = request.session.get('empresa_id')
    logger.info(f"Empresa ID da sessão: {empresa_id}")
    if not empresa_id:
        logger.warning("Empresa não encontrada na sessão")
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    if request.method == 'POST':
        logger.info("Método POST detectado")
        form = FaturamentoMedicoForm(request.POST, request.FILES, empresa_id=empresa_id)
        logger.info(f"Form criado: {form}")
        if form.is_valid():
            logger.info("Form é válido")

            # Processar arquivos com Gemini se foram enviados
            documentos_gemini = request.FILES.getlist('documentos_gemini')
            documento_upload = request.FILES.get('documento_upload')
            dados_gemini = {}

            # Processar documento_upload se enviado
            if documento_upload:
                logger.info("Processando documento_upload com Gemini")
                dados_gemini = processar_arquivos_com_gemini([documento_upload])
                logger.info(f"Dados extraídos do documento_upload: {dados_gemini}")

            # Processar documentos_gemini adicionais se enviados
            elif documentos_gemini:
                logger.info(f"Processando {len(documentos_gemini)} arquivos com Gemini")
                dados_gemini = processar_arquivos_com_gemini(documentos_gemini)
                logger.info(f"Dados extraídos do Gemini: {dados_gemini}")

            faturamento = form.save(commit=False)
            faturamento.empresa_id = empresa_id

            # Preencher campos com dados do Gemini se disponíveis
            if dados_gemini.get('nome'):
                faturamento.nome = dados_gemini['nome']
            if dados_gemini.get('carteirinha'):
                faturamento.carteirinha = dados_gemini['carteirinha']
            if dados_gemini.get('guia'):
                faturamento.guia = dados_gemini['guia']
            if dados_gemini.get('numero_guia_lancada'):
                faturamento.numero_guia_lancada = dados_gemini['numero_guia_lancada']
            if dados_gemini.get('data_autorizacao'):
                # Tentar converter data se possível
                try:
                    from datetime import datetime
                    faturamento.data_autorizacao = datetime.strptime(dados_gemini['data_autorizacao'], '%d/%m/%Y').date()
                except:
                    pass
            if dados_gemini.get('data_internacao_cirurgia'):
                # Tentar converter data se possível
                try:
                    from datetime import datetime
                    faturamento.data = datetime.strptime(dados_gemini['data_internacao_cirurgia'], '%d/%m/%Y').date()
                except:
                    pass
            if dados_gemini.get('local'):
                faturamento.local = dados_gemini['local']
            if dados_gemini.get('medico'):
                faturamento.medico = dados_gemini['medico']
            if dados_gemini.get('anestesista'):
                faturamento.anestesista = dados_gemini['anestesista']
            if dados_gemini.get('convenio'):
                faturamento.convenio = dados_gemini['convenio']
            if dados_gemini.get('apartamento_enfermaria'):
                faturamento.apartamento_enfermaria = dados_gemini['apartamento_enfermaria']
            if dados_gemini.get('urgencia'):
                faturamento.urgencia = dados_gemini['urgencia']

            faturamento.save()
            logger.info(f"Faturamento salvo: {faturamento.id}")

            # Criar itens de serviço baseados nos dados do Gemini
            if dados_gemini.get('servicos'):
                for servico in dados_gemini['servicos']:
                    ItemServico.objects.create(
                        faturamento=faturamento,
                        servico=servico.get('descricao', ''),
                        codigo_servico=servico.get('codigo', ''),
                        valor=servico.get('valor_unitario', 0),
                        qt=servico.get('quantidade', 1)
                    )

            # Anexar documentos processados
            documentos_para_anexar = []
            if documento_upload:
                documentos_para_anexar.append(documento_upload)
            documentos_para_anexar.extend(documentos_gemini)

            for documento in documentos_para_anexar:
                DocumentoAnexado.objects.create(
                    faturamento=faturamento,
                    arquivo=documento,
                    nome=f"Documento Gemini - {documento.name}",
                    descricao="Documento processado com Gemini para extração de dados"
                )

            # Adicionar mensagem de sucesso específica se Gemini foi usado
            if documentos_gemini and dados_gemini:
                messages.success(request, f'Faturamento médico criado com sucesso! {len(documentos_gemini)} documento(s) processado(s) com Gemini.')
            else:
                messages.success(request, 'Faturamento médico criado com sucesso!')
    
                messages.success(request, 'Faturamento médico criado com sucesso!')
                # Redirecionar com filtros preservados
                filters = request.session.get('faturamento_filters', {})
                url = reverse('faturamento_medico:ftlistar')
                if filters:
                    url += '?' + urlencode(filters, doseq=True)
                return redirect(url)
        else:
            logger.warning(f"Form inválido: {form.errors}")
    else:
        logger.info("Método GET detectado")
        initial_data = {
            'data_autorizacao': timezone.now().date(),
            'data': timezone.now().date(),
        }
        form = FaturamentoMedicoForm(empresa_id=empresa_id, initial=initial_data)

    context = {
        'form': form,
        'titulo': 'Criar Faturamento Médico'
    }

    logger.info("Renderizando template form.html")
    return render(request, 'faturamento_medico/form.html', context)


def editar_faturamento(request, pk):
    """Edita um faturamento médico existente"""
    faturamento = get_object_or_404(FaturamentoMedico, pk=pk)
    empresa_id = request.session.get('empresa_id')

    if request.method == 'POST':
        form = FaturamentoMedicoForm(request.POST, instance=faturamento, empresa_id=empresa_id)
        if form.is_valid():
            form.save()
            messages.success(request, 'Faturamento médico atualizado com sucesso!')
            # Redirecionar com filtros preservados
            filters = request.session.get('faturamento_filters', {})
            url = reverse('faturamento_medico:ftlistar')
            if filters:
                url += '?' + urlencode(filters, doseq=True)
            return redirect(url)
    else:
        form = FaturamentoMedicoForm(instance=faturamento, empresa_id=empresa_id)

    context = {
        'form': form,
        'faturamento': faturamento,
        'titulo': 'Editar Faturamento Médico'
    }

    return render(request, 'faturamento_medico/form.html', context)


def excluir_faturamento(request, pk):
    """Exclui um faturamento médico e seus itens vinculados."""
    empresa_id = request.session.get('empresa_id')
    qs = FaturamentoMedico.objects.all()
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    faturamento = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        nome = faturamento.nome or f'#{faturamento.pk}'
        # Itens e documentos são removidos por CASCADE
        faturamento.delete()
        messages.success(request, f'Faturamento médico "{nome}" excluído com sucesso!')
        filters = request.session.get('faturamento_filters', {})
        url = reverse('faturamento_medico:ftlistar')
        if filters:
            # Remove valores vazios para não poluir a query
            limpos = {k: v for k, v in filters.items() if v not in (None, '', [])}
            if limpos:
                url += '?' + urlencode(limpos, doseq=True)
        return redirect(url)

    context = {
        'faturamento': faturamento,
        'titulo': 'Confirmar Exclusão',
    }
    return render(request, 'faturamento_medico/confirmar_exclusao.html', context)


def detalhes_faturamento(request, pk):
    """Exibe detalhes de um faturamento médico"""
    faturamento = get_object_or_404(FaturamentoMedico, pk=pk)

    context = {
        'faturamento': faturamento,
    }

    return render(request, 'faturamento_medico/detalhes.html', context)


def exportar_excel(request):
    """Exporta faturamentos filtrados para Excel (conferência: 1 linha por procedimento)."""
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        faturamentos = (
            FaturamentoMedico.objects
            .filter(empresa_id=empresa_id)
            .prefetch_related('itens_servico')
            .order_by('-data', 'nome')
        )
    else:
        faturamentos = FaturamentoMedico.objects.none()

    filtros = _filtros_listagem_faturamento(request, use_session_fallback=True)
    faturamentos = _aplicar_filtros_faturamento_qs(faturamentos, filtros)
    nome = filtros['nome']
    guia = filtros['guia']
    anestesista = filtros['anestesista']
    status = filtros['status']
    status_conferencia = filtros['status_conferencia']
    lote = filtros['lote']
    data_inicio = filtros['data_inicio']
    data_fim = filtros['data_fim']
    convenios = filtros['convenios']
    codigo_relatorio = filtros['codigo_relatorio']

    # Cache preços para status de conferência
    precos_por_codigo = set()
    precos_por_descricao = set()
    if empresa_id:
        from servicos_medicos.models import TabelaPreco
        for t in (
            TabelaPreco.objects
            .filter(empresa_id=empresa_id)
            .select_related('codigo_servico', 'convenio')
        ):
            conv = (t.convenio.nome or '').strip().upper()
            cod = (t.codigo_servico.codigo or '').strip().upper()
            desc = (t.codigo_servico.servicos or '').strip().upper()
            if conv and cod:
                precos_por_codigo.add((conv, cod))
            if conv and desc:
                precos_por_descricao.add((conv, desc))

    def _tem_preco(faturamento, item):
        if not item:
            return False
        valor = item.total if item.total is not None else item.valor
        if valor is None or valor == 0:
            return False
        conv = (faturamento.convenio or '').strip().upper()
        cod = (item.codigo_servico or '').strip().upper()
        desc = (item.servico or '').strip().upper()
        if cod and (conv, cod) in precos_por_codigo:
            return True
        if desc and (conv, desc) in precos_por_descricao:
            return True
        return False

    wb = Workbook()
    ws = wb.active
    ws.title = "Conferencia"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2B4B7C", end_color="2B4B7C", fill_type="solid")
    empresa_font = Font(bold=True, size=14)
    empresa_fill = PatternFill(start_color="E6E6FA", end_color="E6E6FA", fill_type="solid")

    if empresa_id:
        try:
            empresa = Empresa.objects.get(id=empresa_id)
            empresa_info = f"{empresa.razao} - CNPJ: {empresa.cnpj}"
        except Empresa.DoesNotExist:
            empresa_info = f"Empresa ID: {empresa_id}"
    else:
        empresa_info = "Empresa não identificada"

    ws.cell(row=1, column=1).value = empresa_info
    ws.cell(row=1, column=1).font = empresa_font
    ws.cell(row=1, column=1).fill = empresa_fill

    ws.cell(row=3, column=1).value = "RELATÓRIO DE CONFERÊNCIA - FATURAMENTO MÉDICO"
    ws.cell(row=3, column=1).font = Font(bold=True, size=16)
    ws.cell(row=4, column=1).value = f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws.cell(row=4, column=1).font = Font(italic=True)

    filtros_excel = []
    if nome:
        filtros_excel.append(f"Nome: {nome}")
    if guia:
        filtros_excel.append(f"Guia: {guia}")
    if codigo_relatorio:
        filtros_excel.append(f"Código Relatório: {codigo_relatorio}")
    if anestesista:
        filtros_excel.append(f"Anestesista: {anestesista}")
    if data_inicio:
        filtros_excel.append(f"Data início: {data_inicio}")
    if data_fim:
        filtros_excel.append(f"Data fim: {data_fim}")
    if convenios:
        filtros_excel.append(f"Convênios: {', '.join(convenios)}")
    if status:
        filtros_excel.append(f"Status: {status}")
    if status_conferencia:
        filtros_excel.append(f"Status Conferência: {status_conferencia}")
    if lote == '__sem__':
        filtros_excel.append("Lote: Sem lote")
    elif lote:
        filtros_excel.append(f"Lote: {lote}")
    ws.cell(row=5, column=1).value = (
        "Filtros: " + ("; ".join(filtros_excel) if filtros_excel else "nenhum")
    )
    ws.cell(row=5, column=1).font = Font(italic=True)

    # Colunas alinhadas ao modelo RIS/agenda + campos do banco para conferência
    headers = [
        # Conferência (grid)
        'ID Faturamento',
        'ID Item',
        'Data',
        'Paciente',
        'Nome Associado',
        'Procedimento',
        'Modalidade',
        'Com Contraste',
        'Valor Item',
        'QT',
        'Percentual',
        'Total Item',
        'Conferido',
        'Status Conferencia',
        # Origem agenda / faturamento
        'Unidade/Local',
        'Carteirinha (CNS)',
        'CPF',
        'Prioridade',
        'Horario Inicio',
        'Horario Fim',
        'Horario',
        'Status Agendamento',
        'Motivo Cancelamento/Desistencia/Delecao',
        'Convenio (Viabilidade)',
        'Tag',
        'Agendado Via',
        'Lote',
        'Guia',
        'Codigo Servico Item',
        'Porte Item',
        'Medico',
        'Medico Solicitante',
        'Tecnico',
        'Check-in Por',
        'Agendado Por',
        'Anestesista',
        'Receber Por',
        'Apartamento/Enfermaria',
        'Urgencia',
        'Indicacao Clinica',
        'Descricao',
        'Data Autorizacao',
        'Guia Lancada',
        'Numero Guia Lancada',
        'Nota Fiscal',
        'Codigo Relatorio',
        'Status Faturamento',
        'Codigo Fechamento',
        'Data Fechamento',
        'Percentual Imposto',
        'Valor Imposto',
        'Percentual Comissao',
        'Valor Comissao',
        'Total Faturamento',
        'Observacao',
        'Data Criacao',
        'Data Atualizacao',
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=7, column=col_num)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill

    row_num = 8
    for faturamento in faturamentos:
        itens = list(faturamento.itens_servico.all())
        if not itens:
            status_label, _ = _status_linha_faturamento(faturamento)
            if status_conferencia and status_label != status_conferencia:
                continue
            itens = [None]
        else:
            itens_filtrados = []
            for item in itens:
                status_label, _ = _status_linha_faturamento(faturamento, item)
                if status_conferencia and status_label != status_conferencia:
                    continue
                itens_filtrados.append(item)
            if not itens_filtrados:
                continue
            itens = itens_filtrados

        for item in itens:
            if item is not None:
                status_label, _ = item.status_conferencia_badge()
                conferido = 'Sim' if item.conferido else 'Não'
                procedimento = item.servico or ''
                modalidade = item.modalidade or ''
                com_contraste = 'Sim' if item.com_contraste else 'Não'
                valor_item = float(item.valor) if item.valor is not None else 0
                qt = item.qt or 1
                percentual = float(item.percentual) if item.percentual is not None else 1
                total_item = float(item.total) if item.total is not None else 0
                codigo_item = item.codigo_servico or ''
                porte_item = item.porte or ''
                item_id = item.id
            else:
                if not (faturamento.guia or '').strip():
                    status_label = 'FALTA DE GUIA'
                elif not faturamento.total:
                    status_label = 'FALTA DE VALOR NA TABELA'
                else:
                    status_label = 'PENDENTE'
                conferido = 'Não'
                procedimento = faturamento.servico or ''
                modalidade = ''
                com_contraste = 'Sim' if 'contraste' in (procedimento or '').lower() else 'Não'
                valor_item = float(faturamento.valor) if faturamento.valor else 0
                qt = faturamento.qt or 1
                percentual = 1
                total_item = float(faturamento.total) if faturamento.total else 0
                codigo_item = faturamento.codigo_servico or ''
                porte_item = faturamento.porte or ''
                item_id = ''

            valores = [
                faturamento.id,
                item_id,
                faturamento.data.strftime('%d/%m/%Y') if faturamento.data else '',
                faturamento.nome or '',
                faturamento.nome_associado or faturamento.nome or '',
                procedimento,
                modalidade,
                com_contraste,
                valor_item,
                qt,
                percentual,
                total_item,
                conferido,
                status_label,
                faturamento.local or '',
                faturamento.carteirinha or '',
                faturamento.cpf or '',
                faturamento.prioridade or '',
                faturamento.horario_inicio or '',
                faturamento.horario_fim or '',
                faturamento.horario or '',
                faturamento.status_agendamento or '',
                faturamento.motivo_cancelamento or '',
                faturamento.convenio or '',
                faturamento.tag or '',
                faturamento.agendado_via or '',
                faturamento.lote or '',
                faturamento.guia or '',
                codigo_item,
                porte_item,
                faturamento.medico or '',
                faturamento.medico_solicitante or '',
                faturamento.tecnico or '',
                faturamento.checkin_por or '',
                faturamento.agendado_por or '',
                faturamento.anestesista or '',
                faturamento.receber_por or '',
                faturamento.apartamento_enfermaria or '',
                faturamento.urgencia or '',
                faturamento.indicacao_clinica or '',
                faturamento.descricao or '',
                faturamento.data_autorizacao.strftime('%d/%m/%Y') if faturamento.data_autorizacao else '',
                faturamento.guia_lancada or 0,
                faturamento.numero_guia_lancada or '',
                faturamento.nota_fiscal or '',
                faturamento.codigo_relatorio or '',
                faturamento.status or '',
                faturamento.codigo_fechamento or '',
                faturamento.data_fechamento.strftime('%d/%m/%Y') if faturamento.data_fechamento else '',
                float(faturamento.percentual_imposto or 0),
                float(faturamento.valor_imposto or 0),
                float(faturamento.percentual_comissao or 0),
                float(faturamento.valor_comissao or 0),
                float(faturamento.total) if faturamento.total else 0,
                faturamento.observacao or '',
                faturamento.data_criacao.strftime('%d/%m/%Y %H:%M') if faturamento.data_criacao else '',
                faturamento.data_atualizacao.strftime('%d/%m/%Y %H:%M') if faturamento.data_atualizacao else '',
            ]

            for col_num, valor in enumerate(valores, 1):
                ws.cell(row=row_num, column=col_num).value = valor
            row_num += 1

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                max_length = max(max_length, len(str(cell.value)) if cell.value is not None else 0)
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 40)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename=conferencia_faturamento_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )
    wb.save(response)
    return response


def anexar_documento(request, pk):
    """View para anexar documentos a um faturamento"""
    faturamento = get_object_or_404(FaturamentoMedico, pk=pk)

    if request.method == 'POST':
        form = DocumentoAnexadoForm(request.POST, request.FILES)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.faturamento = faturamento
            documento.save()
            messages.success(request, 'Documento anexado com sucesso!')
            return redirect('faturamento_medico:detalhes', pk=faturamento.pk)
    else:
        form = DocumentoAnexadoForm()

    context = {
        'form': form,
        'faturamento': faturamento,
        'titulo': f'Anexar Documento - {faturamento}'
    }

    return render(request, 'faturamento_medico/anexar_documento.html', context)


def download_documento(request, pk):
    """View para fazer download/visualizar de um documento anexado"""
    documento = get_object_or_404(DocumentoAnexado, pk=pk)

    try:
        with open(documento.arquivo.path, 'rb') as f:
            # Determinar o content_type baseado na extensão
            extensao = documento.arquivo.name.split('.')[-1].lower()
            if extensao == 'pdf':
                content_type = 'application/pdf'
            elif extensao in ['jpg', 'jpeg']:
                content_type = 'image/jpeg'
            elif extensao == 'png':
                content_type = 'image/png'
            elif extensao == 'gif':
                content_type = 'image/gif'
            else:
                content_type = 'application/octet-stream'

            response = HttpResponse(f.read(), content_type=content_type)
            # Se for para visualização inline (ex: PDFs no modal), usar inline
            if request.GET.get('inline') == 'true':
                response['Content-Disposition'] = f'inline; filename="{documento.arquivo.name.split("/")[-1]}"'
            else:
                response['Content-Disposition'] = f'attachment; filename="{documento.arquivo.name.split("/")[-1]}"'
            return response
    except FileNotFoundError:
        raise Http404("Arquivo não encontrado")


def excluir_documento(request, pk):
    """View para excluir um documento anexado"""
    documento = get_object_or_404(DocumentoAnexado, pk=pk)
    faturamento_pk = documento.faturamento.pk

    if request.method == 'POST':
        # Remove o arquivo do sistema de arquivos
        if documento.arquivo:
            documento.arquivo.delete(save=False)
        # Remove o registro do banco
        documento.delete()
        messages.success(request, 'Documento excluído com sucesso!')
        return redirect('faturamento_medico:detalhes', pk=faturamento_pk)

    context = {
        'documento': documento,
    }

    return render(request, 'faturamento_medico/confirmar_exclusao_documento.html', context)


def adicionar_item_servico(request, pk):
    """View para adicionar item de serviço a um faturamento"""
    faturamento = get_object_or_404(FaturamentoMedico, pk=pk)

    if request.method == 'POST':
        form = ItemServicoForm(request.POST, faturamento=faturamento)
        if form.is_valid():
            # Pegar os dados do POST
            cabecalho_id = request.POST.get('cabecalho')
            codigo_servico = request.POST.get('codigo_servico')
            qt = form.cleaned_data.get('qt', 1)
            valor = form.cleaned_data.get('valor', 0)

            if cabecalho_id and codigo_servico:
                from servicos_medicos.models import Cabecalho, ServicosMedicos
                try:
                    cabecalho = Cabecalho.objects.get(id=cabecalho_id)
                    servico = ServicosMedicos.objects.get(codigo=codigo_servico)

                    ItemServico.objects.create(
                        faturamento=faturamento,
                        codigo_servico=servico.codigo,
                        servico=servico.servicos,
                        porte=servico.porte_anestesico,
                        valor=valor,
                        qt=qt
                    )
                    # Atualiza o total do faturamento
                    faturamento.atualizar_total()
                    messages.success(request, 'Item de serviço adicionado com sucesso!')
                    return redirect('faturamento_medico:detalhes', pk=faturamento.pk)
                except (Cabecalho.DoesNotExist, ServicosMedicos.DoesNotExist):
                    messages.error(request, 'Cabeçalho ou serviço não encontrado.')
            else:
                messages.error(request, 'Selecione um cabeçalho e digite um código de serviço.')
    else:
        form = ItemServicoForm(faturamento=faturamento)

    context = {
        'form': form,
        'faturamento': faturamento,
        'titulo': f'Adicionar Item de Serviço - {faturamento}'
    }

    return render(request, 'faturamento_medico/adicionar_item_servico.html', context)


def editar_item_servico(request, pk):
    """View para editar item de serviço"""
    item = get_object_or_404(ItemServico, pk=pk)

    if request.method == 'POST':
        logger.info(f"Editando item {pk}, POST data: {request.POST}")
        # Para edição, cabecalho não é necessário
        post_data = request.POST.copy()
        form = ItemServicoForm(post_data, instance=item, faturamento=item.faturamento)
        logger.info(f"Form is_valid: {form.is_valid()}")
        if form.is_valid():
            logger.info("Salvando form")
            saved_item = form.save()
            logger.info(f"Item salvo: {saved_item.id}, valor: {saved_item.valor}, qt: {saved_item.qt}, total: {saved_item.total}")
            # Atualiza o total do faturamento
            item.faturamento.atualizar_total()
            logger.info(f"Total do faturamento atualizado: {item.faturamento.total}")
            messages.success(request, 'Item de serviço atualizado com sucesso!')
            return redirect('faturamento_medico:detalhes', pk=item.faturamento.pk)
        else:
            logger.error(f"Form errors: {form.errors}")
    else:
        form = ItemServicoForm(instance=item, faturamento=item.faturamento)

    context = {
        'form': form,
        'item': item,
        'faturamento': item.faturamento,
        'titulo': f'Editar Item de Serviço - {item.faturamento}'
    }

    return render(request, 'faturamento_medico/editar_item_servico.html', context)


def excluir_item_servico(request, pk):
    """View para excluir item de serviço"""
    item = get_object_or_404(ItemServico, pk=pk)
    faturamento_pk = item.faturamento.pk

    if request.method == 'POST':
        item.delete()
        # Atualiza o total do faturamento
        item.faturamento.atualizar_total()
        messages.success(request, 'Item de serviço excluído com sucesso!')
        return redirect('faturamento_medico:detalhes', pk=faturamento_pk)

    context = {
        'item': item,
    }

    return render(request, 'faturamento_medico/confirmar_exclusao_item.html', context)


def fechamento_repasse(request):
    """View para fechamento de repasse para anestesista"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:listar')

    # Filtros para seleção
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    convenios = request.GET.getlist('convenio')
    data_fechamento = request.GET.get('data_fechamento')
    anestesista = request.GET.get('anestesista')
    mostrar_fechados = request.GET.get('mostrar_fechados', 'false').lower() == 'true'

    # Buscar convênios disponíveis para a empresa
    convenios_disponiveis = []
    if empresa_id:
        from servicos_medicos.models import Convenio
        convenios_disponiveis = list(Convenio.objects.filter(empresa_id=empresa_id).order_by('nome'))
        if not convenios_disponiveis:
            # Convênios padrão se nenhum for encontrado para a empresa
            convenios_padrao = [
                {'nome': 'CBSAUDE'},
                {'nome': 'PM'},
                {'nome': 'UNIMED'},
                {'nome': 'BRADESCO'},
                {'nome': 'GEAP'},
                {'nome': 'SAUDE CAIXA'},
                {'nome': 'POSTAL SAUDE'},
                {'nome': 'FUSEX'},
                {'nome': 'LIFE EMPRESARIAL'},
                {'nome': 'CASSI'},
                {'nome': 'GCARD'},
                {'nome': 'PERSONAL NET'},
            ]
            convenios_disponiveis = convenios_padrao

    # Query base
    faturamentos = FaturamentoMedico.objects.filter(empresa_id=empresa_id)

    # Aplicar filtros
    if data_inicio:
        faturamentos = faturamentos.filter(data_fechamento__gte=data_inicio)
    if data_fim:
        faturamentos = faturamentos.filter(data_fechamento__lte=data_fim)
    if convenios:
        q_objects = Q()
        for conv in convenios:
            if conv:
                q_objects |= Q(convenio__icontains=conv)
        faturamentos = faturamentos.filter(q_objects)
    if anestesista:
        faturamentos = faturamentos.filter(anestesista__icontains=anestesista)

    # Filtrar apenas faturamentos com anestesista
    faturamentos = faturamentos.exclude(anestesista__isnull=True).exclude(anestesista='')

    # Processar fechamento se for POST
    if request.method == 'POST':
        faturamentos_ids = request.POST.getlist('faturamentos_selecionados')

        if request.POST.get('aplicar_comissao') and faturamentos_ids:
            # Aplicar comissão aos faturamentos selecionados
            percentual_imposto = float(request.POST.get('percentual_imposto', 0))
            percentual_comissao = float(request.POST.get('percentual_comissao', 0))

            # Usar getlist para obter todos os valores do campo
            faturamentos_ids = request.POST.getlist('faturamentos_selecionados')

            # Debug: verificar o que está sendo recebido
            logger.info(f"faturamentos_ids após getlist: {faturamentos_ids} (tipo: {type(faturamentos_ids)})")

            # Converter IDs para inteiros para evitar problemas de tipo
            try:
                faturamentos_ids = [int(id.strip()) for id in faturamentos_ids if id.strip()]
            except (ValueError, TypeError) as e:
                logger.error(f"Erro ao converter IDs: {e}. faturamentos_ids: {faturamentos_ids}")
                messages.error(request, 'IDs de faturamentos inválidos.')
                return redirect('faturamento_medico:fechamento_repasse')

            faturamentos = FaturamentoMedico.objects.filter(
                id__in=faturamentos_ids,
                empresa_id=empresa_id
            )

            for faturamento in faturamentos:
                # Calcular valores com precisão decimal (manter como Decimal)
                from decimal import Decimal
                total_decimal = Decimal(str(faturamento.total))
                percentual_imposto_decimal = Decimal(str(percentual_imposto))
                percentual_comissao_decimal = Decimal(str(percentual_comissao))

                valor_imposto = (total_decimal * percentual_imposto_decimal / 100).quantize(Decimal('0.01'))
                base_comissao = total_decimal - valor_imposto
                valor_comissao = (base_comissao * percentual_comissao_decimal / 100).quantize(Decimal('0.01'))

                # Atualizar campos
                faturamento.percentual_imposto = percentual_imposto
                faturamento.percentual_comissao = percentual_comissao
                faturamento.valor_imposto = valor_imposto
                faturamento.valor_comissao = valor_comissao
                faturamento.save()

            # Verificar se é uma requisição AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'success': True,
                    'message': f'Comissão aplicada com sucesso para {len(faturamentos_ids)} faturamento(s)!'
                })
            else:
                messages.success(request, f'Comissão aplicada com sucesso para {len(faturamentos_ids)} faturamento(s)!')
                return redirect('faturamento_medico:fechamento_repasse')

        elif faturamentos_ids:
            # Usar data atual se não foi fornecida
            if not data_fechamento:
                data_fechamento = timezone.now().date()

            # Gerar código único para este fechamento com bloqueio de transação
            from django.db import transaction
            max_attempts = 10
            attempt = 0
            codigo_fechamento = None

            while attempt < max_attempts:
                codigo_fechamento = str(uuid.uuid4())[:8].upper()
                logger.info(f"Código de fechamento gerado (tentativa {attempt + 1}): {codigo_fechamento}")

                # Verificar se o código já existe
                with transaction.atomic():
                    existing_with_code = FaturamentoMedico.objects.select_for_update().filter(codigo_fechamento=codigo_fechamento)
                    if not existing_with_code.exists():
                        logger.info(f"Código de fechamento único encontrado: {codigo_fechamento}")
                        break
                    else:
                        logger.warning(f"Código de fechamento {codigo_fechamento} já existe em {existing_with_code.count()} registros")
                        attempt += 1

            if attempt >= max_attempts:
                logger.error("Não foi possível gerar um código único após várias tentativas")
                messages.error(request, 'Erro interno: não foi possível gerar código único de fechamento.')
                return redirect('faturamento_medico:fechamento_repasse')

            # Buscar faturamentos selecionados para verificar status
            faturamentos_selecionados = FaturamentoMedico.objects.filter(
                id__in=faturamentos_ids,
                empresa_id=empresa_id
            )
            logger.info(f"Faturamentos selecionados: {len(faturamentos_selecionados)}")

            # Verificar se algum já está fechado
            faturamentos_ja_fechados = faturamentos_selecionados.filter(data_fechamento__isnull=False)
            if faturamentos_ja_fechados.exists():
                logger.warning(f"Encontrados {faturamentos_ja_fechados.count()} faturamentos já fechados:")
                for fat in faturamentos_ja_fechados:
                    logger.warning(f"  ID {fat.id}: data_fechamento={fat.data_fechamento}, codigo_fechamento={fat.codigo_fechamento}")

            # Verificar códigos de fechamento existentes nos faturamentos selecionados
            faturamentos_com_codigo = faturamentos_selecionados.filter(codigo_fechamento__isnull=False)
            if faturamentos_com_codigo.exists():
                logger.info(f"Faturamentos selecionados que já têm código de fechamento:")
                for fat in faturamentos_com_codigo:
                    logger.info(f"  ID {fat.id}: codigo_fechamento={fat.codigo_fechamento}")

            # Atualizar data de fechamento, status e código para os faturamentos selecionados
            # Primeiro, verificar se algum faturamento já tem um código de fechamento
            faturamentos_com_codigo_existente = FaturamentoMedico.objects.filter(
                id__in=faturamentos_ids,
                empresa_id=empresa_id,
                codigo_fechamento__isnull=False
            )

            if faturamentos_com_codigo_existente.exists():
                logger.warning(f"Encontrados {faturamentos_com_codigo_existente.count()} faturamentos que já têm código de fechamento:")
                for fat in faturamentos_com_codigo_existente:
                    logger.warning(f"  ID {fat.id}: codigo_fechamento={fat.codigo_fechamento}")
                # Para estes, não sobrescrever o código existente
                faturamentos_ids_para_atualizar = [id for id in faturamentos_ids if id not in [fat.id for fat in faturamentos_com_codigo_existente]]
                logger.info(f"Atualizando apenas {len(faturamentos_ids_para_atualizar)} faturamentos sem código existente")
            else:
                faturamentos_ids_para_atualizar = faturamentos_ids

            if faturamentos_ids_para_atualizar:
                # SOLUÇÃO DEFINITIVA: Usar códigos únicos por faturamento
                updated_count = 0
                for faturamento_id in faturamentos_ids_para_atualizar:
                    # Gerar código único para cada faturamento
                    faturamento_codigo = str(uuid.uuid4())[:8].upper()

                    try:
                        # Tentar atualizar este faturamento específico com código único
                        count = FaturamentoMedico.objects.filter(
                            id=faturamento_id,
                            empresa_id=empresa_id,
                            codigo_fechamento__isnull=True,  # Só atualizar se não tiver código
                            status__in=['pendente', 'enviado']  # Só atualizar se não estiver finalizado
                        ).update(
                            data_fechamento=data_fechamento,
                            status='finalizado',
                            codigo_fechamento=faturamento_codigo
                        )
                        if count > 0:
                            updated_count += count
                            logger.info(f"Faturamento {faturamento_id} atualizado com código único {faturamento_codigo}")
                        else:
                            logger.warning(f"Faturamento {faturamento_id} não foi atualizado (já processado ou não encontrado)")
                    except Exception as e:
                        logger.error(f"Erro ao atualizar faturamento {faturamento_id}: {e}")
                        # Mesmo com códigos únicos, pode haver race condition, mas é muito improvável
                        raise e

                logger.info(f"Total de faturamentos atualizados com códigos únicos: {updated_count}")
                if updated_count > 0:
                    messages.success(request, f'Fechamento realizado com sucesso! {updated_count} faturamento(s) finalizado(s) com códigos únicos.')
                else:
                    messages.warning(request, 'Nenhum faturamento foi atualizado. Todos podem já ter sido processados.')
            else:
                logger.info("Nenhum faturamento para atualizar (todos já têm código de fechamento)")
                messages.info(request, 'Todos os faturamentos selecionados já possuem código de fechamento.')

            messages.success(request, f'Fechamento realizado com sucesso para {len(faturamentos_ids)} faturamento(s)! Código: {codigo_fechamento}')
            return redirect('faturamento_medico:fechamento_repasse')

    # Filtrar baseado na opção selecionada
    if mostrar_fechados:
        # Mostrar apenas faturamentos já fechados
        faturamentos_filtrados = faturamentos.filter(data_fechamento__isnull=False)
    else:
        # Mostrar apenas faturamentos não fechados (padrão)
        faturamentos_filtrados = faturamentos.filter(data_fechamento__isnull=True)

    # Estatísticas
    total_faturamentos = faturamentos_filtrados.count()
    valor_total = sum(f.total for f in faturamentos_filtrados if f.total)

    context = {
        'faturamentos': faturamentos_filtrados,
        'total_faturamentos': total_faturamentos,
        'valor_total': valor_total,
        'convenios_disponiveis': convenios_disponiveis,
        'filtros': {
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'convenio': convenios,
            'data_fechamento': data_fechamento,
            'anestesista': anestesista,
        },
        'mostrar_fechados': mostrar_fechados,
    }

    return render(request, 'faturamento_medico/fechamento_repasse.html', context)


def reabrir_fechamento(request, pk):
    """View para reabrir um fechamento de repasse"""
    faturamento = get_object_or_404(FaturamentoMedico, pk=pk)

    if request.method == 'POST':
        # Limpar campos de fechamento
        faturamento.data_fechamento = None
        faturamento.status = 'pendente'
        faturamento.codigo_fechamento = None
        # Manter os valores de comissão e imposto calculados
        faturamento.save()

        messages.success(request, f'Fechamento reaberto com sucesso para {faturamento.nome}!')
        return redirect('faturamento_medico:fechamento_repasse')

    context = {
        'faturamento': faturamento,
    }

    return render(request, 'faturamento_medico/confirmar_reabertura.html', context)


def exportar_excel_fechados(request):
    """Exporta os repasses fechados para Excel com cabeçalho da empresa e ordenação por convênio"""
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        faturamentos = FaturamentoMedico.objects.filter(empresa_id=empresa_id)
    else:
        faturamentos = FaturamentoMedico.objects.none()

    # Aplicar os mesmos filtros da view de fechamento_repasse
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    convenios = request.GET.getlist('convenio')
    data_fechamento = request.GET.get('data_fechamento')
    anestesista = request.GET.get('anestesista')

    # Buscar convênios disponíveis para a empresa (para compatibilidade)
    convenios_disponiveis = []
    if empresa_id:
        from servicos_medicos.models import Convenio
        convenios_disponiveis = Convenio.objects.filter(empresa_id=empresa_id).order_by('nome')

    if data_inicio:
        faturamentos = faturamentos.filter(data__gte=data_inicio)
    if data_fim:
        faturamentos = faturamentos.filter(data__lte=data_fim)
    if convenios:
        q_objects = Q()
        for conv in convenios:
            if conv:
                q_objects |= Q(convenio__icontains=conv)
        faturamentos = faturamentos.filter(q_objects)
    if anestesista:
        faturamentos = faturamentos.filter(anestesista__icontains=anestesista)

    # Filtrar apenas faturamentos com anestesista e fechados
    faturamentos = faturamentos.exclude(anestesista__isnull=True).exclude(anestesista='')
    faturamentos = faturamentos.filter(data_fechamento__isnull=False)

    # Ordenar por convênio
    faturamentos = faturamentos.order_by('convenio', 'data')

    # Criar workbook Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Repasses Fechados"

    # Estilo do cabeçalho
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")

    # Estilo para cabeçalho da empresa
    empresa_font = Font(bold=True, size=14)
    empresa_fill = PatternFill(start_color="E6E6FA", end_color="E6E6FA", fill_type="solid")

    # Informações básicas da empresa
    if empresa_id:
        try:
            empresa = Empresa.objects.get(id=empresa_id)
            empresa_info = f"{empresa.razao} - CNPJ: {empresa.cnpj}"
        except Empresa.DoesNotExist:
            empresa_info = f"Empresa ID: {empresa_id} - Dados não encontrados"
    else:
        empresa_info = "Empresa não identificada"

    # Adicionar cabeçalho da empresa
    ws.cell(row=1, column=1).value = empresa_info
    ws.cell(row=1, column=1).font = empresa_font
    ws.cell(row=1, column=1).fill = empresa_fill

    # Título do relatório
    ws.cell(row=3, column=1).value = "RELATÓRIO DE REPASSES FECHADOS"
    ws.cell(row=3, column=1).font = Font(bold=True, size=16)

    # Data de geração
    from datetime import datetime
    ws.cell(row=4, column=1).value = f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws.cell(row=4, column=1).font = Font(italic=True)

    # Filtros aplicados
    filtros_texto = "Filtros aplicados:"
    if data_inicio:
        filtros_texto += f" Data início: {data_inicio}"
    if data_fim:
        filtros_texto += f" Data fim: {data_fim}"
    if data_fechamento:
        filtros_texto += f" Data fechamento: {data_fechamento}"
    if convenios:
        filtros_texto += f" Convênios: {', '.join(convenios)}"
    if anestesista:
        filtros_texto += f" Anestesista: {anestesista}"

    ws.cell(row=5, column=1).value = filtros_texto
    ws.cell(row=5, column=1).font = Font(italic=True)

    # Cabeçalhos dos dados (linha 7)
    headers = [
        'Data', 'Nome', 'Guia', 'Anestesista', 'Convênio','Codigo Relatorio' ,'Código Serviço', 'Serviço', 'QT', 'Valor Unitário',
        'Valor Total Item','Valor Total', 'Valor do Imposto', 'Valor da Comissão', 'Valor Líquido',
        'Data de Fechamento', 'Status'
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=7, column=col_num)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
    # Dados (a partir da linha 8)
    current_row = 8
    for faturamento in faturamentos:
        # Buscar itens de serviço para este faturamento
        valor_liquido = float(faturamento.total or 0) - float(faturamento.valor_imposto or 0) - float(faturamento.valor_comissao or 0)
        ws.cell(row=current_row, column=1).value = faturamento.data.strftime('%d/%m/%Y') if faturamento.data else ''
        ws.cell(row=current_row, column=2).value = faturamento.nome or ''
        ws.cell(row=current_row, column=3).value = faturamento.guia or ''
        ws.cell(row=current_row, column=4).value = faturamento.anestesista or ''
        ws.cell(row=current_row, column=5).value = faturamento.convenio or ''
        ws.cell(row=current_row, column=6).value = faturamento.codigo_relatorio or ''
        itens_servico = faturamento.itens_servico.filter(faturamento_id = faturamento.id)

        if itens_servico.exists():
            # Para cada item de serviço, criar uma linha
            cont = 0;
            for item in itens_servico:
                # Calcular valor líquido
                

                
                ws.cell(row=current_row, column=7).value = item.codigo_servico or ''
                ws.cell(row=current_row, column=8).value = item.servico or ''
                ws.cell(row=current_row, column=9).value = item.qt or 0
                ws.cell(row=current_row, column=10).value = float(item.valor) if item.valor else 0
                ws.cell(row=current_row, column=11).value = float(item.total) if item.total else 0
                
                if cont == 0:
                   ws.cell(row=current_row, column=12).value = float(faturamento.total) if faturamento.total else 0   
                   ws.cell(row=current_row, column=13).value = float(faturamento.valor_imposto) if faturamento.valor_imposto else 0
                   ws.cell(row=current_row, column=14).value = float(faturamento.valor_comissao) if faturamento.valor_comissao else 0
                   ws.cell(row=current_row, column=15).value = valor_liquido
                   ws.cell(row=current_row, column=16).value = faturamento.data_fechamento.strftime('%d/%m/%Y') if faturamento.data_fechamento else ''
                   
                   ws.cell(row=current_row, column=17).value = faturamento.status or ''    
                cont += 1
                current_row += 1
        
        cont = 0 
        
        current_row += 1

    # Ajustar largura das colunas
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Resposta HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=repasses_fechados.xlsx'

    wb.save(response)
    return response


# Views para Serviços Disponíveis
def listar_servicos(request):
    """Lista todos os serviços disponíveis"""
    servicos = ServicoDisponivel.objects.all().order_by('codigo')

    # Filtros
    categoria = request.GET.get('categoria')
    ativo = request.GET.get('ativo')

    if categoria:
        servicos = servicos.filter(categoria__icontains=categoria)
    if ativo:
        if ativo == '1':
            servicos = servicos.filter(ativo=True)
        elif ativo == '0':
            servicos = servicos.filter(ativo=False)

    context = {
        'servicos': servicos,
        'filtros': {
            'categoria': categoria,
            'ativo': ativo,
        }
    }

    return render(request, 'faturamento_medico/listar_servicos.html', context)


def criar_servico(request):
    """Cria um novo serviço disponível"""
    if request.method == 'POST':
        form = ServicoDisponivelForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Serviço criado com sucesso!')
            return redirect('faturamento_medico:listar_servicos')
    else:
        form = ServicoDisponivelForm()

    context = {
        'form': form,
        'titulo': 'Criar Serviço Disponível'
    }

    return render(request, 'faturamento_medico/form_servico.html', context)


def editar_servico(request, pk):
    """Edita um serviço disponível existente"""
    servico = get_object_or_404(ServicoDisponivel, pk=pk)

    if request.method == 'POST':
        form = ServicoDisponivelForm(request.POST, instance=servico)
        if form.is_valid():
            form.save()
            messages.success(request, 'Serviço atualizado com sucesso!')
            return redirect('faturamento_medico:listar_servicos')
    else:
        form = ServicoDisponivelForm(instance=servico)

    context = {
        'form': form,
        'servico': servico,
        'titulo': 'Editar Serviço Disponível'
    }

    return render(request, 'faturamento_medico/form_servico.html', context)
def extrair_dados_documento(request):
    """View para extrair dados de documento usando Gemini via AJAX"""
    if request.method == 'POST':
        documento = request.FILES.get('documento')
        if documento:
            dados = processar_arquivos_com_gemini([documento])
            logger.info(f"Dados extraídos para debug: {dados}")
            return JsonResponse(dados)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def extrair_dados_documento_ocr(request):
    """View para extrair dados de documento usando OCR via AJAX"""
    if request.method == 'POST':
        documento = request.FILES.get('documento')
        if documento:
            dados = processar_arquivos_com_ocr([documento])
            logger.info(f"Dados extraídos via OCR para debug: {dados}")
            return JsonResponse(dados)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def excluir_servico(request, pk):
    """Exclui um serviço disponível"""
    servico = get_object_or_404(ServicoDisponivel, pk=pk)

    if request.method == 'POST':
        servico.delete()
        messages.success(request, 'Serviço excluído com sucesso!')
        return redirect('faturamento_medico:listar_servicos')

    context = {
        'servico': servico,
    }

    return render(request, 'faturamento_medico/confirmar_exclusao_servico.html', context)


def carregar_tabelas_por_cabecalho(request, cabecalho_id):
    """View AJAX para carregar tabelas por cabeçalho"""
    try:
        from servicos_medicos.models import Cabecalho, TabelaPreco
        cabecalho = Cabecalho.objects.get(id=cabecalho_id)
        tabelas = TabelaPreco.objects.filter(cabecalho=cabecalho).select_related('codigo_servico')
        data = []
        for tabela in tabelas:
            data.append({
                'id': tabela.id,
                'codigo': tabela.codigo_servico.codigo,
                'servico': tabela.codigo_servico.servicos,
                'porte': tabela.codigo_servico.porte_anestesico,
                'preco_apartamento': str(tabela.preco_apartamento),
                'preco_enfermaria': str(tabela.preco_enfermaria),
                'display': f"{tabela.codigo_servico} - {tabela.preco_apartamento}/{tabela.preco_enfermaria}"
            })
        return JsonResponse({'success': True, 'tabelas': data})
    except Cabecalho.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Cabeçalho não encontrado'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def buscar_servicos(request):
    """View AJAX para buscar serviços por código"""
    query = request.GET.get('q', '')
    if len(query) >= 3:  # Buscar a partir de 3 caracteres
        from servicos_medicos.models import ServicosMedicos
        servicos = ServicosMedicos.objects.filter(codigo__icontains=query)[:10]  # Limitar a 10 resultados
        data = []
        for servico in servicos:
            data.append({
                'codigo': servico.codigo,
                'servico': servico.servicos,
                'porte': servico.porte_anestesico
            })
        return JsonResponse({'success': True, 'servicos': data})
    return JsonResponse({'success': True, 'servicos': []})


def buscar_servicos_por_descricao(request):
    """View AJAX para buscar serviços por descrição"""
    query = request.GET.get('q', '')
    if len(query) >= 3:  # Buscar a partir de 3 caracteres
        from servicos_medicos.models import ServicosMedicos
        servicos = ServicosMedicos.objects.filter(servicos__icontains=query)[:10]  # Limitar a 10 resultados
        data = []
        for servico in servicos:
            data.append({
                'codigo': servico.codigo,
                'servico': servico.servicos,
                'porte': servico.porte_anestesico
            })
        return JsonResponse({'success': True, 'servicos': data})
    return JsonResponse({'success': True, 'servicos': []})


def buscar_precos_servico(request, cabecalho_id, codigo_servico):
    """View AJAX para buscar preços de um serviço em um cabeçalho"""
    try:
        from servicos_medicos.models import Cabecalho, TabelaPreco, ServicosMedicos
        cabecalho = Cabecalho.objects.get(id=cabecalho_id)
        servico = ServicosMedicos.objects.get(codigo=codigo_servico)
        tabela = TabelaPreco.objects.filter(
            cabecalho=cabecalho,
            codigo_servico=servico
        ).first()
        if tabela:
            return JsonResponse({
                'success': True,
                'preco_apartamento': str(tabela.preco_apartamento),
                'preco_enfermaria': str(tabela.preco_enfermaria)
            })
        else:
            return JsonResponse({
                'success': True,
                'preco_apartamento': '0.00',
                'preco_enfermaria': '0.00'
            })
    except (Cabecalho.DoesNotExist, ServicosMedicos.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Cabeçalho ou serviço não encontrado'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def selecionar_lote_imprimir(request):
    """View para selecionar lote para imprimir relatório"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    lotes = Lote.objects.filter(empresa_id=empresa_id).order_by('-id')
    context = {'lotes': lotes}
    return render(request, 'faturamento_medico/selecionar_lote_imprimir.html', context)


def imprimir_lote(request, lote_id):
    """View para imprimir relatório de lote em HTML"""
    if lote_id == 0:
        lote_id = request.GET.get('lote_id')
        if not lote_id:
            return HttpResponse('Lote não selecionado')

    lote = get_object_or_404(Lote, id=lote_id)
    empresa_id = request.GET.get('empresa_id') or request.session.get('empresa_id')
    if not empresa_id:
        return HttpResponse('Sessão expirada. Faça login novamente.')
    # Verificar se o lote pertence à empresa (já filtrado na seleção)
    if lote.empresa_id != int(empresa_id):
        return HttpResponse('Acesso negado')

    faturamentos = FaturamentoMedico.objects.filter(lote=str(lote.id)).order_by('data')
    items = ItemServico.objects.filter(faturamento__in=faturamentos).select_related('faturamento').order_by('faturamento__nome', 'faturamento__data', 'faturamento__guia')

    # Agrupar itens por beneficiário
    grouped_items = {}
    total_geral = 0
    for item in items:
        beneficiario = item.faturamento.nome or 'Sem Nome'
        if beneficiario not in grouped_items:
            grouped_items[beneficiario] = []
        grouped_items[beneficiario].append(item)
        total_geral += item.total or 0

    empresa = Empresa.objects.get(id=empresa_id)

    from django.db.models import Min, Max
    periodo_inicio = faturamentos.aggregate(min_data=Min('data'))['min_data']
    periodo_fim = faturamentos.aggregate(max_data=Max('data'))['max_data']

    context = {
        'lote': lote,
        'empresa': empresa,
        'periodo_inicio': periodo_inicio,
        'periodo_fim': periodo_fim,
        'grouped_items': grouped_items,
        'total_geral': total_geral,
    }
    return render(request, 'faturamento_medico/imprimir_lote.html', context)


def imprimir_repasses_fechados(request):
    """View para imprimir relatório de repasses fechados em HTML"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return HttpResponse('Sessão expirada. Faça login novamente.')

    # Aplicar os mesmos filtros da view de fechamento_repasse
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    convenios = request.GET.getlist('convenio')
    data_fechamento = request.GET.get('data_fechamento')
    anestesista = request.GET.get('anestesista')

    # Query base - apenas faturamentos fechados com anestesista
    faturamentos = FaturamentoMedico.objects.filter(
        empresa_id=empresa_id,
        data_fechamento__isnull=False,
        anestesista__isnull=False
    ).exclude(anestesista='').order_by('anestesista', 'data_fechamento', 'nome')

    # Aplicar filtros
    if data_inicio:
        faturamentos = faturamentos.filter(data_fechamento__gte=data_inicio)
    if data_fim:
        faturamentos = faturamentos.filter(data_fechamento__lte=data_fim)
    if convenios:
        q_objects = Q()
        for conv in convenios:
            if conv:
                q_objects |= Q(convenio__icontains=conv)
        faturamentos = faturamentos.filter(q_objects)
    if anestesista:
        faturamentos = faturamentos.filter(anestesista__icontains=anestesista)

    # Agrupar por anestesista
    repasses_por_anestesista = {}
    total_geral = 0
    total_imposto_geral = 0
    total_comissao_geral = 0
    total_liquido_geral = 0

    for faturamento in faturamentos:
        anestesista_nome = faturamento.anestesista or 'Sem Anestesista'
        if anestesista_nome not in repasses_por_anestesista:
            repasses_por_anestesista[anestesista_nome] = {
                'repasses': [],
                'total_valor_total': 0,
                'total_valor_imposto': 0,
                'total_valor_comissao': 0,
                'total_valor_liquido': 0,
            }

        # Calcular valores
        valor_total = float(faturamento.total or 0)
        valor_imposto = float(faturamento.valor_imposto or 0)
        valor_comissao = float(faturamento.valor_comissao or 0)
        valor_liquido = valor_total - valor_imposto - valor_comissao

        repasse_info = {
            'faturamento': faturamento,
            'valor_total': valor_total,
            'valor_imposto': valor_imposto,
            'valor_comissao': valor_comissao,
            'valor_liquido': valor_liquido,
        }

        repasses_por_anestesista[anestesista_nome]['repasses'].append(repasse_info)
        repasses_por_anestesista[anestesista_nome]['total_valor_total'] += valor_total
        repasses_por_anestesista[anestesista_nome]['total_valor_imposto'] += valor_imposto
        repasses_por_anestesista[anestesista_nome]['total_valor_comissao'] += valor_comissao
        repasses_por_anestesista[anestesista_nome]['total_valor_liquido'] += valor_liquido

        # Acumuladores gerais
        total_geral += valor_total
        total_imposto_geral += valor_imposto
        total_comissao_geral += valor_comissao
        total_liquido_geral += valor_liquido

    empresa = Empresa.objects.get(id=empresa_id)

    # Calcular período
    from django.db.models import Min, Max
    periodo_inicio = faturamentos.aggregate(min_data=Min('data_fechamento'))['min_data']
    periodo_fim = faturamentos.aggregate(max_data=Max('data_fechamento'))['max_data']

    context = {
        'empresa': empresa,
        'periodo_inicio': periodo_inicio,
        'periodo_fim': periodo_fim,
        'repasses_por_anestesista': repasses_por_anestesista,
        'total_geral': total_geral,
        'total_imposto_geral': total_imposto_geral,
        'total_comissao_geral': total_comissao_geral,
        'total_liquido_geral': total_liquido_geral,
        'filtros': {
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'convenio': convenios,
            'data_fechamento': data_fechamento,
            'anestesista': anestesista,
        }
    }

    return render(request, 'faturamento_medico/imprimir_repasses_fechados.html', context)


def carregar_precos_por_cabecalho(request, cabecalho_id):
    """View AJAX para carregar preços por cabeçalho"""
    try:
        from servicos_medicos.models import Cabecalho, TabelaPreco
        cabecalho = Cabecalho.objects.get(id=cabecalho_id)
        # Pegar os preços do primeiro serviço ou calcular médias, mas como são por serviço, talvez mostrar uma mensagem
        tabelas = TabelaPreco.objects.filter(cabecalho=cabecalho)
        if tabelas.exists():
            # Como os preços variam por serviço, talvez mostrar uma mensagem ou os preços do primeiro
            preco_apartamento = tabelas.first().preco_apartamento
            preco_enfermaria = tabelas.first().preco_enfermaria
            return JsonResponse({
                'success': True,
                'preco_apartamento': str(preco_apartamento),
                'preco_enfermaria': str(preco_enfermaria)
            })
        else:
            return JsonResponse({'success': False, 'error': 'Nenhuma tabela encontrada'})
    except Cabecalho.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Cabeçalho não encontrado'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def gerar_lote(request):
    """View para gerar lote a partir dos faturamentos selecionados"""
    logger.info("Iniciando gerar_lote")
    empresa_id = request.session.get('empresa_id')
    logger.info(f"Empresa ID da sessão: {empresa_id}")
    if not empresa_id:
        logger.warning("Empresa não encontrada na sessão")
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    if request.method == 'POST':
        logger.info("Método POST detectado")
        faturamento_ids = request.POST.getlist('faturamentos_selecionados')
        lote_existente_id = request.POST.get('lote_existente')
        logger.info(f"Faturamento IDs selecionados: {faturamento_ids}")
        logger.info(f"Lote existente: {lote_existente_id}")

        if not faturamento_ids:
            logger.warning("Nenhum faturamento selecionado")
            messages.error(request, 'Selecione pelo menos um faturamento para gerar o lote.')
            return redirect('faturamento_medico:ftlistar')

        # Buscar faturamentos selecionados
        faturamentos = FaturamentoMedico.objects.filter(
            id__in=faturamento_ids,
            empresa_id=empresa_id
        )
        logger.info(f"Faturamentos encontrados: {faturamentos.count()}")

        if not faturamentos.exists():
            logger.warning("Nenhum faturamento encontrado para os IDs")
            messages.error(request, 'Nenhum faturamento encontrado.')
            return redirect('faturamento_medico:ftlistar')

        if lote_existente_id:
            # Adicionar a lote existente
            try:
                lote_existente = Lote.objects.get(id=lote_existente_id, empresa_id=empresa_id)
                logger.info(f"Adicionando a lote existente: {lote_existente.id}")
            except Lote.DoesNotExist:
                logger.error(f"Lote existente não encontrado: {lote_existente_id}")
                messages.error(request, 'Lote selecionado não encontrado.')
                return redirect('faturamento_medico:ftlistar')

            # Verificar se os faturamentos têm o mesmo convênio do lote
            faturamentos_diferente_convenio = faturamentos.exclude(convenio=lote_existente.convenio)
            if faturamentos_diferente_convenio.exists():
                logger.warning(f"Faturamentos com convênio diferente: {[f.id for f in faturamentos_diferente_convenio]}")
                messages.error(request, 'Todos os faturamentos devem ter o mesmo convênio do lote selecionado.')
                return redirect('faturamento_medico:ftlistar')

            # Filtrar faturamentos sem lote ou com status != finalizado
            faturamentos_validos = faturamentos.filter(status__in=['pendente', 'enviado'])
            faturamentos_invalidos = faturamentos.exclude(status__in=['pendente', 'enviado'])

            if faturamentos_invalidos.exists():
                logger.warning(f"Faturamentos com status finalizado: {[f.id for f in faturamentos_invalidos]}")
                messages.warning(request, 'Faturamentos finalizados não podem ser adicionados a lotes.')

            if not faturamentos_validos.exists():
                logger.warning("Nenhum faturamento válido para adicionar")
                messages.error(request, 'Nenhum faturamento válido para adicionar ao lote.')
                return redirect('faturamento_medico:ftlistar')

            # Atualizar os faturamentos com o ID do lote e status para enviado
            fat_ids = [f.id for f in faturamentos_validos]
            try:
                updated = FaturamentoMedico.objects.filter(id__in=fat_ids).update(lote=str(lote_existente.id), status='enviado')
                logger.info(f"Faturamentos adicionados ao lote {lote_existente.id}: {updated}")
            except Exception as e:
                logger.error(f"Erro ao adicionar faturamentos ao lote {lote_existente.id}: {e}")
                messages.error(request, f'Erro ao adicionar faturamentos ao lote: {e}')
                return redirect('faturamento_medico:ftlistar')

            # Atualizar o total do lote
            try:
                lote_existente.atualizar_total()
                lote_existente.sincronizar_extrato_pagamento()
                logger.info(f"Total do lote {lote_existente.id} atualizado: {lote_existente.total_lote}")
            except Exception as e:
                logger.error(f"Erro ao atualizar total do lote {lote_existente.id}: {e}")
                messages.error(request, f'Erro ao atualizar total do lote: {e}')
                return redirect('faturamento_medico:ftlistar')

            url = reverse('faturamento_medico:ftlistar')
            return HttpResponse(f'<script>alert("Faturamentos adicionados ao lote {lote_existente.id} com sucesso!"); window.location.href = "{url}";</script>')
        else:
            # Criar novo lote
            # Filtrar apenas faturamentos sem lote
            faturamentos_sem_lote = faturamentos.filter(lote__isnull=True) | faturamentos.filter(lote='')
            faturamentos_com_lote = faturamentos.exclude(lote__isnull=True).exclude(lote='')

            if faturamentos_com_lote.exists():
                logger.warning(f"Alguns faturamentos já têm lote: {[f.id for f in faturamentos_com_lote]}")
                messages.warning(request, f'Alguns faturamentos selecionados já estão incluídos em outro lote e foram ignorados.')

            if not faturamentos_sem_lote.exists():
                logger.warning("Nenhum faturamento sem lote encontrado")
                messages.error(request, 'Todos os faturamentos selecionados já estão incluídos em lotes.')
                return redirect('faturamento_medico:ftlistar')

            faturamentos = faturamentos_sem_lote
            logger.info(f"Faturamentos sem lote: {faturamentos.count()}")

            # Agrupar faturamentos por convênio
            faturamentos_por_convenio = {}
            for fat in faturamentos:
                convenio = fat.convenio or 'Sem Convênio'
                if convenio not in faturamentos_por_convenio:
                    faturamentos_por_convenio[convenio] = []
                faturamentos_por_convenio[convenio].append(fat)

            logger.info(f"Faturamentos agrupados por convênio: { {k: len(v) for k, v in faturamentos_por_convenio.items()} }")

            lotes_criados = []
            for convenio, fats in faturamentos_por_convenio.items():
                logger.info(f"Criando lote para convênio: {convenio}")

                # Criar o lote
                try:
                    lote = Lote.objects.create(
                        empresa_id=empresa_id,
                        convenio=convenio if convenio != 'Sem Convênio' else None
                    )
                    logger.info(f"Lote criado: {lote.id} para convênio {convenio}")
                except Exception as e:
                    logger.error(f"Erro ao criar lote para convênio {convenio}: {e}")
                    messages.error(request, f'Erro ao criar lote para convênio {convenio}: {e}')
                    continue

                # Atualizar os faturamentos com o ID do lote e status para enviado
                fat_ids = [f.id for f in fats]
                try:
                    updated = FaturamentoMedico.objects.filter(id__in=fat_ids).update(lote=str(lote.id), status='enviado')
                    logger.info(f"Faturamentos atualizados para lote {lote.id}: {updated}")
                except Exception as e:
                    logger.error(f"Erro ao atualizar faturamentos para lote {lote.id}: {e}")
                    messages.error(request, f'Erro ao atualizar faturamentos para lote {lote.id}: {e}')
                    continue

                # Atualizar o total do lote
                try:
                    lote.atualizar_total()
                    lote.sincronizar_extrato_pagamento()
                    logger.info(f"Total do lote {lote.id} atualizado: {lote.total_lote}")
                except Exception as e:
                    logger.error(f"Erro ao atualizar total do lote {lote.id}: {e}")
                    messages.error(request, f'Erro ao atualizar total do lote {lote.id}: {e}')
                    continue

                lotes_criados.append(lote.id)

            if lotes_criados:
                url = reverse('faturamento_medico:ftlistar')
                logger.info(f"Lotes criados: {lotes_criados}")
                lotes_str = ', '.join(map(str, lotes_criados))
                return HttpResponse(f'<script>alert("Lotes gerados com sucesso: {lotes_str}"); window.location.href = "{url}";</script>')
            else:
                logger.warning("Nenhum lote foi criado")
                messages.error(request, 'Nenhum lote foi criado.')
                return redirect('faturamento_medico:ftlistar')

    logger.info("Método não é POST, redirecionando")
    return redirect('faturamento_medico:ftlistar')


def importar_unimed(request):
    """View para importar relatório UNIMED"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            messages.error(request, 'Selecione um arquivo para importar.')
            return redirect('faturamento_medico:importar_unimed')

        try:
            # Ler o arquivo
            content = arquivo.read().decode('utf-8')
            lines = content.split('\n')

            # Pular cabeçalho
            data_lines = lines[1:]

            # Agrupar por lote e guia
            grupos = {}
            servicos_unicos = set()

            for line in data_lines:
                if not line.strip():
                    continue
                parts = line.split(';')
                if len(parts) < 13:
                    continue

                lote = parts[0].strip()
                guia = parts[1].strip()
                cod_usuario = parts[2].strip()
                nome_usuario = parts[3].strip()
                plano = parts[4].strip()
                cod_servico = parts[5].strip()
                desc_servico = parts[6].strip()
                tp_grau = parts[7].strip()
                data_str = parts[8].strip()
                qtde_via = parts[9].strip()
                percentual = parts[10].strip().replace(',', '.')
                valor_unit = parts[11].strip().replace(',', '.')
                valor_total = parts[12].strip().replace(',', '.')
                cod_rel = parts[13].strip()
                observacao = parts[14].strip() if len(parts) > 12 else ''

                # Converter data
                try:
                    data = datetime.strptime(data_str, '%d/%m/%Y').date()
                except:
                    data = timezone.now().date()

                chave = f"{lote}_{guia}"

                if chave not in grupos:
                    grupos[chave] = {
                        'lote': lote,
                        'guia': guia,
                        'carteirinha': cod_usuario,
                        'nome': nome_usuario,
                        'plano': plano,
                        'data': data,
                        'cod_rel': cod_rel,
                        'servicos': []
                    }

                grupos[chave]['servicos'].append({
                    'codigo': cod_servico,
                    'descricao': desc_servico,
                    'porte': tp_grau,
                    'qt': int(float(qtde_via)) if qtde_via else 1,
                    'percentual': float(percentual) if percentual else 0,
                    'valor': float(valor_unit) if valor_unit else 0,
                    'total': float(valor_total) if valor_total else 0,
                    'observacao': observacao
                })

                servicos_unicos.add((cod_servico, desc_servico))

            # Verificar e criar serviços não cadastrados
            from servicos_medicos.models import ServicosMedicos
            servicos_criados = 0
            for cod, desc in servicos_unicos:
                if not ServicosMedicos.objects.filter(codigo=cod).exists():
                    ServicosMedicos.objects.create(
                        codigo=cod,
                        servicos=desc,
                        porte_anestesico=None  # Será definido depois se necessário
                    )
                    servicos_criados += 1

            # Criar faturamentos
            faturamentos_criados = 0
            itens_criados = 0

            for chave, dados in grupos.items():
                # Criar faturamento
                faturamento = FaturamentoMedico.objects.create(
                    empresa_id=empresa_id,
                    lote=dados['lote'],
                    guia=dados['guia'],
                    carteirinha=dados['carteirinha'],
                    nome=dados['nome'],
                    data=dados['data'],
                    convenio='UNIMED',
                    codigo_relatorio=dados['cod_rel'],
                    status='pendente'
                )

                # Criar itens de serviço
                for servico in dados['servicos']:
                    ItemServico.objects.create(
                        faturamento=faturamento,
                        codigo_servico=servico['codigo'],
                        servico=servico['descricao'],
                        porte=servico['porte'],
                        percentual = servico['percentual'],
                        qt=servico['qt'],
                        valor=servico['valor'],
                        total=servico['total']
                    )
                    itens_criados += 1

                # Atualizar total do faturamento
                faturamento.atualizar_total()
                faturamentos_criados += 1

            messages.success(request, f'Importação concluída! {servicos_criados} serviços criados, {faturamentos_criados} faturamentos criados, {itens_criados} itens de serviço criados.')

        except Exception as e:
            messages.error(request, f'Erro durante a importação: {str(e)}')
            return redirect('faturamento_medico:importar_unimed')

        return redirect('faturamento_medico:ftlistar')

    context = {
        'titulo': 'Importar Relatório UNIMED'
    }

    return render(request, 'faturamento_medico/importar_unimed.html', context)


def importar_xml(request):
    """View para importar XML de NFSe"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    if request.method == 'POST':
        arquivos = request.FILES.getlist('arquivos')
        if not arquivos:
            messages.error(request, 'Selecione pelo menos um arquivo XML para importar.')
            return redirect('faturamento_medico:importar_xml')

        try:
            import xml.etree.ElementTree as ET
            from servicos_medicos.models import ServicosMedicos

            faturamentos_criados = 0
            itens_criados = 0
            servicos_criados = 0
            servicos_unicos = set()

            for arquivo in arquivos:
                # Parse do XML
                content = arquivo.read().decode('utf-8')
                root = ET.fromstring(content)

                # Namespace do XML
                ns = {'nfse': 'http://www.abrasf.org.br/nfse.xsd'}

                # Encontrar o elemento Nfse
                nfse = root.find('.//nfse:Nfse', ns)
                if nfse is None:
                    continue

                inf_nfse = nfse.find('nfse:InfNfse', ns)
                if inf_nfse is None:
                    continue

                # Extrair dados básicos
                numero = inf_nfse.findtext('nfse:Numero', default='')
                data_emissao_str = inf_nfse.findtext('nfse:DataEmissao', default='')
                outras_info = inf_nfse.findtext('nfse:OutrasInformacoes', default='')

                # Valores NFSe
                valores_nfse = inf_nfse.find('nfse:ValoresNfse', ns)
                valor_liquido = 0.0
                if valores_nfse is not None:
                    valor_liquido_str = valores_nfse.findtext('nfse:ValorLiquidoNfse', default='0')
                    try:
                        valor_liquido = float(valor_liquido_str)
                    except:
                        valor_liquido = 0.0

                # Prestador
                prestador_servico = inf_nfse.find('nfse:PrestadorServico', ns)
                prestador_cnpj = ''
                prestador_razao = ''
                if prestador_servico is not None:
                    identificacao = prestador_servico.find('nfse:IdentificacaoPrestador', ns)
                    if identificacao is not None:
                        cpf_cnpj = identificacao.find('nfse:CpfCnpj', ns)
                        if cpf_cnpj is not None:
                            prestador_cnpj = cpf_cnpj.findtext('nfse:Cnpj', default='')
                    prestador_razao = prestador_servico.findtext('nfse:RazaoSocial', default='')

                # Tomador
                declaracao = inf_nfse.find('nfse:DeclaracaoPrestacaoServico', ns)
                tomador_nome = ''
                tomador_cpf = ''
                if declaracao is not None:
                    inf_declaracao = declaracao.find('nfse:InfDeclaracaoPrestacaoServico', ns)
                    if inf_declaracao is not None:
                        tomador = inf_declaracao.find('nfse:Tomador', ns)
                        if tomador is not None:
                            tomador_nome = tomador.findtext('nfse:RazaoSocial', default='')
                            identificacao_tomador = tomador.find('nfse:IdentificacaoTomador', ns)
                            if identificacao_tomador is not None:
                                cpf_cnpj_tomador = identificacao_tomador.find('nfse:CpfCnpj', ns)
                                if cpf_cnpj_tomador is not None:
                                    tomador_cpf = cpf_cnpj_tomador.findtext('nfse:Cpf', default='')

                        # Serviço
                        servico = inf_declaracao.find('nfse:Servico', ns)
                        if servico is not None:
                            discriminacao = servico.findtext('nfse:Discriminacao', default='')
                            item_lista = servico.findtext('nfse:ItemListaServico', default='')
                            codigo_cnae = servico.findtext('nfse:CodigoCnae', default='')
                            competencia_str = inf_declaracao.findtext('nfse:Competencia', default='')

                            # Valores do serviço
                            valores_servico = servico.find('nfse:Valores', ns)
                            valor_servicos = 0.0
                            if valores_servico is not None:
                                valor_servicos_str = valores_servico.findtext('nfse:ValorServicos', default='0')
                                try:
                                    valor_servicos = float(valor_servicos_str)
                                except:
                                    valor_servicos = 0.0

                            # Converter datas
                            data_emissao = None
                            try:
                                if data_emissao_str:
                                    data_emissao = datetime.fromisoformat(data_emissao_str.replace('Z', '+00:00'))
                            except:
                                data_emissao = timezone.now()

                            competencia = None
                            try:
                                if competencia_str:
                                    competencia = datetime.strptime(competencia_str, '%Y-%m-%d').date()
                            except:
                                competencia = data_emissao.date() if data_emissao else timezone.now().date()

                            # Criar faturamento
                            faturamento = FaturamentoMedico.objects.create(
                                empresa_id=empresa_id,
                                guia=numero,
                                nome=tomador_nome,
                                carteirinha=tomador_cpf,
                                data=competencia or timezone.now().date(),
                                data_autorizacao=data_emissao.date() if data_emissao else None,
                                total=valor_liquido,
                                convenio='NFSE',
                                codigo_relatorio='1',
                                status='pendente',
                                observacao=f"{discriminacao}\n{outras_info}".strip()
                            )

                            # Criar item de serviço
                            ItemServico.objects.create(
                                faturamento=faturamento,
                                codigo_servico=item_lista,
                                servico=discriminacao,
                                porte='',  # NFSe não tem porte anestésico
                                qt=1,
                                valor=valor_servicos,
                                total=valor_liquido
                            )
                            itens_criados += 1

                            # Adicionar serviço único para possível criação
                            servicos_unicos.add((item_lista, discriminacao))

                            faturamentos_criados += 1

            # Verificar e criar serviços não cadastrados
            for cod, desc in servicos_unicos:
                if cod and not ServicosMedicos.objects.filter(codigo=cod).exists():
                    ServicosMedicos.objects.create(
                        codigo=cod,
                        servicos=desc,
                        porte_anestesico=None
                    )
                    servicos_criados += 1

            messages.success(request, f'Importação XML concluída! {servicos_criados} serviços criados, {faturamentos_criados} faturamentos criados, {itens_criados} itens de serviço criados.')

        except Exception as e:
            messages.error(request, f'Erro durante a importação XML: {str(e)}')
            return redirect('faturamento_medico:importar_xml')

        return redirect('faturamento_medico:ftlistar')

    context = {
        'titulo': 'Importar XML NFSe'
    }

    return render(request, 'faturamento_medico/importar_xml.html', context)


RIS_HEADERS = [
    'Unidade',
    'Data',
    'Paciente',
    'Cartão Nacional de Saúde',
    'CPF',
    'Cor/Raça',
    'Idade',
    'E-mail',
    'Telefone',
    'Número do lote',
    'Procedimento',
    'Prioridade',
    'Horário de início',
    'Horário de fim',
    'Modalidade',
    'Valor',
    'Agendado via',
    'Acréscimo/Desconto',
    'Valor pago',
    'Observações de Pagamento',
    'Status do Agendamento',
    'Motivo Cancelamento/Desistência/Deleção',
    'Médico',
    'Médico solicitante',
    'Técnico',
    'Check-in por',
    'Agendado por',
    'Viabilidade',
    'Tag',
    'Indicação clínica',
    'Descrição',
]


def _parse_data_ris(valor):
    """Converte data do Excel RIS para date."""
    if valor is None or valor == '':
        return timezone.now().date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return timezone.now().date()


def _parse_valor_ris(valor):
    """Converte valor monetário do Excel RIS para Decimal."""
    if valor is None or valor == '':
        return Decimal('0')
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace('R$', '').replace(' ', '')
    if ',' in texto and '.' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _celula_texto(valor, max_len=None):
    if valor is None:
        return ''
    texto = str(valor).strip()
    if max_len:
        return texto[:max_len]
    return texto


def baixar_modelo_ris(request):
    """Disponibiliza o modelo próprio RIS (.xlsx) para download."""
    from django.conf import settings
    import os

    caminho = os.path.join(
        settings.BASE_DIR,
        'faturamento_medico',
        'static',
        'faturamento_medico',
        'modelo_ris.xlsx',
    )
    if os.path.exists(caminho):
        with open(caminho, 'rb') as f:
            response = HttpResponse(
                f.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = 'attachment; filename="modelo_ris.xlsx"'
            return response

    # Fallback: gera o modelo em memória
    wb = Workbook()
    ws = wb.active
    ws.title = 'Relatório'
    for i, header in enumerate(RIS_HEADERS, 1):
        ws.cell(1, i, header)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="modelo_ris.xlsx"'
    return response


def importar_ris(request):
    """View para importar relatório no modelo próprio RIS (.xlsx)."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            messages.error(request, 'Selecione um arquivo para importar.')
            return redirect('faturamento_medico:importar_ris')

        nome_arquivo = (arquivo.name or '').lower()
        if not nome_arquivo.endswith(('.xlsx', '.xlsm')):
            messages.error(request, 'Envie um arquivo Excel no modelo RIS (.xlsx).')
            return redirect('faturamento_medico:importar_ris')

        try:
            wb = load_workbook(filename=BytesIO(arquivo.read()), data_only=True)
            ws = wb.active

            headers = []
            for cell in next(ws.iter_rows(min_row=1, max_row=1)):
                headers.append(_celula_texto(cell.value).lower())

            def idx(*nomes):
                for nome in nomes:
                    nome_l = nome.lower()
                    if nome_l in headers:
                        return headers.index(nome_l)
                return None

            col = {
                'unidade': idx('Unidade'),
                'data': idx('Data'),
                'paciente': idx('Paciente'),
                'cns': idx('Cartão Nacional de Saúde', 'Cartao Nacional de Saude'),
                'cpf': idx('CPF'),
                'lote': idx('Número do lote', 'Numero do lote'),
                'procedimento': idx('Procedimento'),
                'prioridade': idx('Prioridade'),
                'horario_inicio': idx('Horário de início', 'Horario de inicio'),
                'horario_fim': idx('Horário de fim', 'Horario de fim'),
                'modalidade': idx('Modalidade'),
                'valor': idx('Valor'),
                'agendado_via': idx('Agendado via', 'Agendado Via'),
                'status': idx('Status do Agendamento'),
                'motivo_cancelamento': idx(
                    'Motivo Cancelamento/Desistência/Deleção',
                    'Motivo Cancelamento/Desistencia/Delecao',
                ),
                'medico': idx('Médico', 'Medico'),
                'medico_solicitante': idx('Médico solicitante', 'Medico solicitante'),
                'tecnico': idx('Técnico', 'Tecnico'),
                'checkin_por': idx('Check-in por', 'Check-in Por'),
                'agendado_por': idx('Agendado por', 'Agendado Por'),
                'convenio': idx('Viabilidade'),
                'tag': idx('Tag'),
                'indicacao': idx('Indicação clínica', 'Indicacao clinica'),
                'descricao': idx('Descrição', 'Descricao'),
                'obs_pagamento': idx('Observações de Pagamento', 'Observacoes de Pagamento'),
            }

            obrigatorias = ['data', 'paciente', 'procedimento', 'valor']
            faltando = [c for c in obrigatorias if col[c] is None]
            if faltando:
                messages.error(
                    request,
                    'Arquivo fora do modelo RIS. Colunas obrigatórias não encontradas: '
                    + ', '.join(faltando)
                    + '. Baixe o modelo próprio RIS e use esse layout.'
                )
                return redirect('faturamento_medico:importar_ris')

            status_ignorar = set()  # Cancelado/Desistência/Deletado passam a ser importados
            grupos = {}
            linhas_ignoradas = 0
            linhas_canceladas = 0

            def get(row, chave):
                i = col.get(chave)
                if i is None or i >= len(row):
                    return None
                return row[i]

            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not any(row):
                    continue

                status_raw = _celula_texto(get(row, 'status'), 50)
                status = status_raw.lower()
                if status in status_ignorar:
                    linhas_ignoradas += 1
                    continue

                paciente = _celula_texto(get(row, 'paciente'), 200)
                procedimento = _celula_texto(get(row, 'procedimento'), 200)
                if not paciente or not procedimento:
                    linhas_ignoradas += 1
                    continue

                data_fat = _parse_data_ris(get(row, 'data'))
                cpf = _celula_texto(get(row, 'cpf'), 50)
                cns = _celula_texto(get(row, 'cns'), 50)
                convenio = _celula_texto(get(row, 'convenio'), 100) or 'Particular'
                # Carteirinha = apenas CNS (não usar CPF)
                carteirinha = cns or None
                valor = _parse_valor_ris(get(row, 'valor'))
                eh_cancelado = _eh_status_agendamento_cancelado(status_raw)
                if eh_cancelado:
                    linhas_canceladas += 1

                # Separa cancelados da lista principal no agrupamento
                chave = f"{paciente}|{data_fat.isoformat()}|{cpf}|{convenio}|{status_raw or 'ok'}"
                modalidade = _celula_texto(get(row, 'modalidade'), 20)
                agendado_via = _celula_texto(get(row, 'agendado_via'), 50) or 'RIS'
                if chave not in grupos:
                    horario_inicio = _celula_texto(get(row, 'horario_inicio'), 20) or None
                    horario_fim = _celula_texto(get(row, 'horario_fim'), 20) or None
                    horario = ''
                    if horario_inicio or horario_fim:
                        horario = f"{(horario_inicio or '')} - {(horario_fim or '')}".strip(' -')
                    status_agendamento = status_raw or None
                    indicacao = _celula_texto(get(row, 'indicacao')) or None
                    descricao = _celula_texto(get(row, 'descricao')) or None
                    obs_pag = _celula_texto(get(row, 'obs_pagamento'))
                    observacao = f"Pagamento: {obs_pag}" if obs_pag else None

                    prioridade = _celula_texto(get(row, 'prioridade'), 50) or None
                    urgencia = 'Não'
                    if prioridade and prioridade.lower() not in ('eletivo', ''):
                        urgencia = 'Sim'

                    grupos[chave] = {
                        'lote': _celula_texto(get(row, 'lote'), 50) or None,
                        'carteirinha': carteirinha,
                        'cpf': cpf or None,
                        'horario': horario or None,
                        'horario_inicio': horario_inicio,
                        'horario_fim': horario_fim,
                        'prioridade': prioridade,
                        'status_agendamento': status_agendamento,
                        'motivo_cancelamento': _celula_texto(get(row, 'motivo_cancelamento'), 255) or None,
                        'nome': paciente,
                        'nome_associado': paciente,
                        'data': data_fat,
                        'local': _celula_texto(get(row, 'unidade'), 200) or None,
                        'medico': _celula_texto(get(row, 'medico'), 200) or None,
                        'medico_solicitante': _celula_texto(get(row, 'medico_solicitante'), 200) or None,
                        'tecnico': _celula_texto(get(row, 'tecnico'), 200) or None,
                        'checkin_por': _celula_texto(get(row, 'checkin_por'), 200) or None,
                        'agendado_por': _celula_texto(get(row, 'agendado_por'), 200) or None,
                        'convenio': convenio,
                        'tag': _celula_texto(get(row, 'tag'), 100) or None,
                        'indicacao_clinica': indicacao,
                        'descricao': descricao,
                        'agendado_via': agendado_via,
                        'urgencia': urgencia,
                        'observacao': observacao,
                        'servicos': [],
                    }

                grupos[chave]['servicos'].append({
                    'descricao': procedimento,
                    'modalidade': modalidade,
                    'com_contraste': 'contraste' in procedimento.lower(),
                    'valor': valor,
                    'total': valor,
                })

            faturamentos_criados = 0
            itens_criados = 0

            for dados in grupos.values():
                faturamento = FaturamentoMedico.objects.create(
                    empresa_id=empresa_id,
                    lote=dados['lote'],
                    carteirinha=dados['carteirinha'],
                    cpf=dados['cpf'],
                    horario=dados['horario'],
                    horario_inicio=dados['horario_inicio'],
                    horario_fim=dados['horario_fim'],
                    prioridade=dados['prioridade'],
                    status_agendamento=dados['status_agendamento'],
                    motivo_cancelamento=dados['motivo_cancelamento'],
                    nome=dados['nome'],
                    nome_associado=dados.get('nome_associado') or dados['nome'],
                    data=dados['data'],
                    local=dados['local'],
                    medico=dados['medico'],
                    medico_solicitante=dados['medico_solicitante'],
                    tecnico=dados['tecnico'],
                    checkin_por=dados['checkin_por'],
                    agendado_por=dados['agendado_por'],
                    convenio=dados['convenio'],
                    tag=dados['tag'],
                    indicacao_clinica=dados['indicacao_clinica'],
                    descricao=dados['descricao'],
                    agendado_via=dados['agendado_via'],
                    urgencia=dados['urgencia'],
                    observacao=dados['observacao'],
                    codigo_relatorio=None,
                    status='pendente',
                )

                for servico in dados['servicos']:
                    ItemServico.objects.create(
                        faturamento=faturamento,
                        codigo_servico='',
                        servico=servico['descricao'],
                        modalidade=servico['modalidade'] or None,
                        com_contraste=servico['com_contraste'],
                        porte='',
                        qt=1,
                        valor=servico['valor'],
                        total=servico['total'],
                    )
                    itens_criados += 1

                faturamento.atualizar_total()
                faturamentos_criados += 1

            msg = (
                f'Importação RIS concluída! '
                f'{faturamentos_criados} faturamentos criados, '
                f'{itens_criados} itens de serviço criados.'
            )
            if linhas_canceladas:
                msg += (
                    f' {linhas_canceladas} linhas Cancelado/Desistência/Deletado '
                    f'(disponíveis em Procedimentos Cancelados).'
                )
            if linhas_ignoradas:
                msg += f' {linhas_ignoradas} linhas ignoradas (vazias).'
            messages.success(request, msg)

        except Exception as e:
            logger.exception('Erro ao importar relatório RIS')
            messages.error(request, f'Erro durante a importação RIS: {str(e)}')
            return redirect('faturamento_medico:importar_ris')

        return redirect('faturamento_medico:ftlistar')

    context = {
        'titulo': 'Importar Relatório RIS'
    }

    return render(request, 'faturamento_medico/importar_ris.html', context)


def sincronizar_medcloud(request):
    """Importa agendas concluídas e/ou links de laudo via API MedCloud."""
    empresa_id = request.session.get('empresa_id')
    try:
        empresa_id = int(empresa_id) if empresa_id is not None else None
    except (TypeError, ValueError):
        empresa_id = None

    if not empresa_id:
        messages.error(request, 'Selecione uma empresa antes de sincronizar com a MedCloud.')
        return redirect('faturamento_medico:ftlistar')

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    hoje = timezone.localdate()
    convenios = Convenio.objects.filter(empresa_id=empresa_id).order_by('nome')

    if request.method == 'POST':
        from faturamento_medico.medcloud.client import MedcloudAPIError
        from faturamento_medico.medcloud.sync import (
            sincronizar_agendas_concluidas,
            sincronizar_links_laudos,
        )

        acao = (request.POST.get('acao') or 'ambos').strip()
        convenio = (request.POST.get('convenio') or '').strip() or None

        def _parse_data_campo(nome, padrao):
            raw = (request.POST.get(nome) or '').strip()
            if not raw:
                return padrao
            try:
                return datetime.strptime(raw, '%Y-%m-%d').date()
            except ValueError:
                return padrao

        data_inicio = _parse_data_campo('data_inicio', hoje)
        data_fim = _parse_data_campo('data_fim', data_inicio)
        if data_fim < data_inicio:
            data_inicio, data_fim = data_fim, data_inicio

        partes_msg = []
        try:
            if acao in ('agendas', 'ambos'):
                stats = sincronizar_agendas_concluidas(
                    empresa,
                    data_inicio,
                    data_fim,
                    convenio_nome=convenio,
                )
                partes_msg.append(
                    f'Agendas: {stats["listadas"]} listadas, '
                    f'{stats.get("importadas", stats.get("concluidas", 0))} importadas, '
                    f'{stats["criadas"]} criadas, {stats["atualizadas"]} atualizadas, '
                    f'{stats["ignoradas"]} ignoradas.'
                )
            if acao in ('laudos', 'ambos'):
                stats = sincronizar_links_laudos(
                    empresa,
                    data_inicio,
                    data_fim,
                    convenio_nome=convenio,
                )
                partes_msg.append(
                    f'Laudos: {stats["atualizados"]} links gravados, '
                    f'{stats["sem_laudo"]} ainda sem laudo, '
                    f'{stats["pulados_link_valido"]} já com link válido.'
                )
            messages.success(request, 'Sincronização MedCloud concluída. ' + ' '.join(partes_msg))
        except MedcloudAPIError as exc:
            messages.error(request, f'MedCloud: {exc}')
        except Exception as exc:
            logger.exception('Erro na sincronização MedCloud')
            messages.error(request, f'Erro na sincronização MedCloud: {exc}')

        return redirect('faturamento_medico:sincronizar_medcloud')

    context = {
        'titulo': 'Sincronizar MedCloud (API)',
        'convenios': convenios,
        'data_hoje': hoje.isoformat(),
    }
    return render(request, 'faturamento_medico/sincronizar_medcloud.html', context)


def toggle_conferencia_item(request, pk):
    """Marca/desmarca conferência de um item de serviço (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método não permitido'}, status=405)

    empresa_id = request.session.get('empresa_id')
    try:
        empresa_id = int(empresa_id) if empresa_id is not None else None
    except (TypeError, ValueError):
        empresa_id = None

    item = get_object_or_404(ItemServico.objects.select_related('faturamento'), pk=pk)
    if empresa_id is not None and item.faturamento.empresa_id != empresa_id:
        return JsonResponse({'ok': False, 'erro': 'Sem permissão'}, status=403)

    # Aceita estado explícito do checkbox; senão faz toggle
    conferido_param = request.POST.get('conferido')
    if conferido_param is not None:
        item.conferido = str(conferido_param).lower() in ('1', 'true', 'sim', 'yes')
    else:
        item.conferido = not item.conferido

    if item.conferido:
        item.status_conferencia = 'CONFERIDO'
    elif item.status_conferencia == 'CONFERIDO':
        item.status_conferencia = 'PENDENTE'

    item.save(update_fields=['conferido', 'status_conferencia', 'total'])
    status_label, status_css = item.status_conferencia_badge()
    return JsonResponse({
        'ok': True,
        'conferido': item.conferido,
        'status': status_label,
        'status_css': status_css,
    })


def alterar_status_conferencia_item(request, pk):
    """Altera manualmente o status de conferência (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método não permitido'}, status=405)

    empresa_id = request.session.get('empresa_id')
    try:
        empresa_id = int(empresa_id) if empresa_id is not None else None
    except (TypeError, ValueError):
        empresa_id = None

    item = get_object_or_404(ItemServico.objects.select_related('faturamento'), pk=pk)
    if empresa_id is not None and item.faturamento.empresa_id != empresa_id:
        return JsonResponse({'ok': False, 'erro': 'Sem permissão'}, status=403)

    status = request.POST.get('status') or ''
    status_label, status_css = item.aplicar_status_conferencia(status)
    return JsonResponse({
        'ok': True,
        'conferido': item.conferido,
        'status': status_label,
        'status_css': status_css,
    })


def listar_extrato_pagamento(request):
    """Lista extrato de pagamento importado por convênio."""
    from django.db.models import Sum

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    qs = ExtratoPagamentoConvenio.objects.filter(empresa_id=empresa_id)

    competencia = (request.GET.get('competencia') or '').strip()
    convenio = (request.GET.get('convenio') or '').strip()
    if competencia:
        qs = qs.filter(competencia=competencia)
    if convenio:
        qs = qs.filter(convenio__icontains=convenio)

    totais = qs.aggregate(
        total_valor=Sum('valor'),
        total_glosado=Sum('valor_glosado'),
        total_liberado=Sum('valor_liberado'),
        total_retencoes=Sum('retencoes'),
        total_recebido=Sum('valor_recebido'),
    )

    competencias = (
        ExtratoPagamentoConvenio.objects.filter(empresa_id=empresa_id)
        .exclude(competencia='')
        .values_list('competencia', flat=True)
        .distinct()
        .order_by('-competencia')
    )

    context = {
        'titulo': 'Extrato de Pagamento — Convênio',
        'linhas': qs.order_by('-data_recebimento', '-competencia', 'lote'),
        'filtros': {'competencia': competencia, 'convenio': convenio},
        'competencias': competencias,
        'totais': totais,
    }
    return render(request, 'faturamento_medico/listar_extrato_pagamento.html', context)


def importar_extrato_pagamento_bradesco(request):
    """Importa Demonstrativo de Pagamento TISS Bradesco Saúde (PDF)."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    def _parse_data_sessao(val):
        if not val:
            return None
        if isinstance(val, date):
            return val
        try:
            return date.fromisoformat(str(val)[:10])
        except (TypeError, ValueError):
            return None

    preview = None
    if request.method == 'POST':
        acao = request.POST.get('acao', 'preview')
        competencia = (request.POST.get('competencia') or '').strip()

        if acao == 'confirmar':
            dados_json = request.session.pop('extrato_pagamento_preview', None)
            if not dados_json:
                messages.error(request, 'Prévia expirada. Importe o PDF novamente.')
                return redirect('faturamento_medico:importar_extrato_pagamento_bradesco')
            competencia_sessao = (dados_json.get('competencia') or competencia or '').strip()
            if not competencia_sessao:
                messages.error(request, 'Competência não informada. Refaça a importação informando MM/AAAA.')
                return redirect('faturamento_medico:importar_extrato_pagamento_bradesco')
            criados = 0
            ignorados = 0
            for row in dados_json.get('linhas', []):
                try:
                    ExtratoPagamentoConvenio.objects.create(
                        empresa_id=empresa_id,
                        competencia=competencia_sessao,
                        convenio=row.get('convenio') or 'BRADESCO SAUDE',
                        data_lote=_parse_data_sessao(row.get('data_lote')),
                        lote=row.get('lote') or '',
                        protocolo=row.get('protocolo') or '',
                        qt_guias=row.get('qt_guias'),
                        valor=Decimal(str(row.get('valor') or 0)),
                        valor_processado=Decimal(str(row.get('valor_processado') or 0)),
                        valor_glosado=Decimal(str(row.get('valor_glosado') or 0)),
                        valor_liberado=Decimal(str(row.get('valor_liberado') or 0)),
                        retencoes=Decimal(str(row.get('retencoes') or 0)),
                        liquido=Decimal(str(row.get('liquido') or 0)),
                        data_previsao=_parse_data_sessao(row.get('data_previsao')),
                        numero_demonstrativo=row.get('numero_demonstrativo') or '',
                        nome_arquivo=dados_json.get('nome_arquivo') or '',
                    )
                    criados += 1
                except Exception:
                    ignorados += 1
            messages.success(
                request,
                f'Importação concluída: {criados} protocolo(s) gravado(s) na competência {competencia_sessao}'
                + (f', {ignorados} duplicado(s) ignorado(s).' if ignorados else '.'),
            )
            return redirect('faturamento_medico:listar_extrato_pagamento')

        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            messages.error(request, 'Selecione o PDF do demonstrativo.')
            return redirect('faturamento_medico:importar_extrato_pagamento_bradesco')

        try:
            from .bradesco_tiss_pdf import parse_extrato_pagamento_bradesco, _parse_competencia

            parsed = parse_extrato_pagamento_bradesco(
                arquivo,
                competencia=competencia,
                nome_arquivo=arquivo.name,
            )
            competencia_final = (
                _parse_competencia(competencia)
                or parsed['cabecalho'].get('competencia')
                or _parse_competencia(arquivo.name)
                or ''
            )
            linhas_sessao = []
            for row in parsed['linhas']:
                row_copy = dict(row)
                row_copy['competencia'] = competencia_final
                linhas_sessao.append({
                    k: (
                        v.isoformat() if hasattr(v, 'isoformat')
                        else float(v) if isinstance(v, Decimal)
                        else v
                    )
                    for k, v in row_copy.items()
                })
            cab_serializado = {
                k: (v.isoformat() if hasattr(v, 'isoformat') else v)
                for k, v in parsed['cabecalho'].items()
            }
            request.session['extrato_pagamento_preview'] = {
                'cabecalho': cab_serializado,
                'linhas': linhas_sessao,
                'nome_arquivo': arquivo.name,
                'competencia': competencia_final,
            }
            linhas_preview = []
            for row in parsed['linhas']:
                r = dict(row)
                r['competencia'] = competencia_final
                linhas_preview.append(r)
            preview = {
                'cabecalho': parsed['cabecalho'],
                'linhas': linhas_preview,
                'nome_arquivo': arquivo.name,
                'competencia': competencia_final,
                'qtd_protocolos': len(parsed['linhas']),
            }
        except Exception as e:
            logger.exception('Erro ao importar extrato pagamento Bradesco')
            messages.error(request, f'Erro ao ler PDF: {e}')
            return redirect('faturamento_medico:importar_extrato_pagamento_bradesco')

    context = {
        'titulo': 'Importar Extrato de Pagamento — Bradesco Saúde',
        'preview': preview,
        'competencia_padrao': (request.POST.get('competencia') or request.GET.get('competencia') or '').strip(),
    }
    return render(request, 'faturamento_medico/importar_extrato_pagamento.html', context)


def baixar_extrato_pagamento(request, pk):
    """Baixa manual — concilia recebimento com extrato bancário."""
    from extrato.models import Banco

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    extrato = get_object_or_404(ExtratoPagamentoConvenio, pk=pk, empresa_id=empresa_id)
    bancos = Banco.objects.order_by('nome')

    if request.method == 'POST':
        data_receb = request.POST.get('data_recebimento')
        valor_raw = (request.POST.get('valor_recebido') or '').strip()
        banco = (request.POST.get('banco') or '').strip()

        if not data_receb or not valor_raw or not banco:
            messages.error(request, 'Informe data de recebimento, valor recebido e banco.')
            return redirect('faturamento_medico:baixar_extrato_pagamento', pk=pk)

        try:
            from emprestimos.sicoob_pdf import _dec
            extrato.data_recebimento = date.fromisoformat(data_receb)
            extrato.valor_recebido = _dec(valor_raw)
            extrato.banco = banco
            extrato.save(update_fields=['data_recebimento', 'valor_recebido', 'banco', 'data_atualizacao'])
            messages.success(request, 'Baixa registrada com sucesso.')
            return redirect('faturamento_medico:listar_extrato_pagamento')
        except (ValueError, InvalidOperation):
            messages.error(request, 'Data ou valor inválido.')
            return redirect('faturamento_medico:baixar_extrato_pagamento', pk=pk)

    sugestao_valor = extrato.liquido or extrato.valor_liberado or Decimal('0')
    context = {
        'titulo': 'Baixar recebimento — Extrato convênio',
        'extrato': extrato,
        'bancos': bancos,
        'sugestao_valor': sugestao_valor,
        'data_hoje': timezone.now().date().isoformat(),
    }
    return render(request, 'faturamento_medico/baixar_extrato_pagamento.html', context)


def estornar_baixa_extrato_pagamento(request, pk):
    """Remove baixa para permitir nova conciliação."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('faturamento_medico:ftlistar')

    if request.method != 'POST':
        return redirect('faturamento_medico:listar_extrato_pagamento')

    extrato = get_object_or_404(ExtratoPagamentoConvenio, pk=pk, empresa_id=empresa_id)
    extrato.data_recebimento = None
    extrato.valor_recebido = Decimal('0')
    extrato.banco = ''
    extrato.save(update_fields=['data_recebimento', 'valor_recebido', 'banco', 'data_atualizacao'])
    messages.success(request, 'Baixa estornada.')
    return redirect('faturamento_medico:listar_extrato_pagamento')

