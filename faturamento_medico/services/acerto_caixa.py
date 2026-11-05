"""Montagem de dados para a tela Acerto de Caixa."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from urllib.parse import urlencode

from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from cobranca.models import Cobranca
from faturamento_medico.lote_relatorio import (
    _inferir_modalidade,
    _modalidade_item,
    _normalizar_codigo_modalidade,
)
from faturamento_medico.log_status_conferencia import registrar_log_status_conferencia_item
from faturamento_medico.models import (
    AcertoCaixaFechamento,
    CAIXAS_ACERTO_VALORES,
    FaturamentoMedico,
    ItemServico,
    rotulo_caixa_acerto,
)
from faturamento_medico.services.contas_caixa_acerto import (
    caixa_valor_ativo_no_acerto,
    caixas_acerto_choices,
    caixas_acerto_valores,
)
from faturamento_medico.services.valor_pago_exibicao import valor_pago_para_exibicao
from faturamento_medico.services.vincular_nota_solicitante import (
    carregar_notas_por_data,
    notas_linha_para_json,
    resolver_notas_linha,
)

STATUS_CANCELADOS = (
    'Cancelado',
    'Desistência',
    'Desistencia',
    'Deletado',
    'Deleção',
    'Delecao',
)

MODALIDADES_RESUMO_ACERTO = (
    ('US', 'QUANTIDADE DE ULTRASSONOGRAFIA'),
    ('CT', 'QUANTIDADE DE TOMOGRAFIA'),
    ('MG', 'QUANTIDADE DE MAMOGRAFIA'),
    ('CR', 'QUANTIDADE DE RAIO X'),
    ('MR', 'QUANTIDADE DE RESSONÂNCIA'),
    ('EG', 'QUANTIDADE DE ELETROENCEFALOGRAMA'),
    ('EC', 'QUANTIDADE DE ELETROCARDIOGRAMA'),
)

MODALIDADES_LABEL_CURTO_ACERTO = {
    'US': 'Ultrassonografia',
    'CT': 'Tomografia',
    'MG': 'Mamografia',
    'CR': 'Raio X',
    'MR': 'Ressonância',
    'EG': 'EEG',
    'EC': 'ECG',
    'OUTROS': 'Outras modalidades',
}

_CODIGOS_MODALIDADE_RESUMO_ACERTO = frozenset(c for c, _ in MODALIDADES_RESUMO_ACERTO)


def _codigo_modalidade_para_resumo_acerto(linha: dict) -> str:
    """Normaliza modalidade da linha para contagem no resumo (inclui inferência pelo procedimento)."""
    bruto = (linha.get('modalidade') or '').strip()
    codigo = _normalizar_codigo_modalidade(bruto)
    if codigo == '-':
        codigo = ''
    if codigo in _CODIGOS_MODALIDADE_RESUMO_ACERTO:
        return codigo
    if codigo == 'RM':
        return 'MR'
    if codigo == 'TC':
        return 'CT'
    inferido = _normalizar_codigo_modalidade(
        _inferir_modalidade(linha.get('procedimento') or '', bruto)
    )
    if inferido and inferido != '-' and inferido in _CODIGOS_MODALIDADE_RESUMO_ACERTO:
        return inferido
    if codigo:
        return codigo
    if inferido and inferido != '-':
        return inferido
    return bruto.upper() if bruto else '-'


def _q_status_cancelados():
    q = Q()
    for status in STATUS_CANCELADOS:
        q |= Q(status_agendamento__iexact=status)
    return q


def _parse_data_filtro(valor) -> date | None:
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor if 2000 <= valor.year <= 2100 else None
    texto = (valor or '').strip()
    if not texto:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            d = datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
        if 2000 <= d.year <= 2100:
            return d
    return None


def _periodo_padrao(hoje: date | None = None) -> tuple[date, date]:
    hoje = hoje or date.today()
    ini = hoje.replace(day=1)
    fim = _ultimo_dia_mes(ini)
    return ini, fim


def _ultimo_dia_mes(d: date) -> date:
    proximo = d.replace(day=28) + timedelta(days=4)
    return proximo - timedelta(days=proximo.day)


MESES_REGUA_PT = (
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

DIAS_SEMANA_CURTO = ('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')

MESES_BOTAO_CURTO = (
    '',
    'Jan',
    'Fev',
    'Mar',
    'Abr',
    'Mai',
    'Jun',
    'Jul',
    'Ago',
    'Set',
    'Out',
    'Nov',
    'Dez',
)


def _botoes_meses_ano(
    filtros: dict, data_inicio: date, data_fim: date, ano: int
) -> list[dict]:
    """Um botão por mês do ano (período = mês inteiro), preservando filtros GET."""
    botoes = []
    for mes in range(1, 13):
        ini = date(ano, mes, 1)
        fim = _ultimo_dia_mes(ini)
        ativo = data_inicio == ini and data_fim == fim
        parcial = (
            not ativo
            and data_inicio <= fim
            and data_fim >= ini
            and (data_inicio != ini or data_fim != fim)
        )
        botoes.append(
            {
                'mes': mes,
                'label': MESES_BOTAO_CURTO[mes],
                'ativo': ativo,
                'parcial': parcial,
                'url_query': url_query_acerto_caixa(filtros, ini, fim),
            }
        )
    return botoes


def _botoes_anos(
    filtros: dict,
    data_inicio: date,
    data_fim: date,
    ano_central: int,
    *,
    raio: int = 4,
) -> list[dict]:
    """Botões de ano (período = ano inteiro), centrados no ano da régua."""
    botoes = []
    for ano in range(ano_central - raio, ano_central + raio + 1):
        ini = date(ano, 1, 1)
        fim = _ultimo_dia_mes(date(ano, 12, 1))
        ativo = data_inicio == ini and data_fim == fim
        parcial = (
            not ativo
            and data_inicio <= fim
            and data_fim >= ini
            and (data_inicio != ini or data_fim != fim)
        )
        botoes.append(
            {
                'ano': ano,
                'label': str(ano),
                'ativo': ativo,
                'parcial': parcial,
                'url_query': url_query_acerto_caixa(filtros, ini, fim),
            }
        )
    return botoes


def url_query_acerto_caixa(filtros: dict, data_inicio: date, data_fim: date) -> str:
    """Query string GET preservando filtros e alterando só o período."""
    pares: list[tuple[str, str]] = [
        ('data_inicio', data_inicio.isoformat()),
        ('data_fim', data_fim.isoformat()),
    ]
    for chave in ('caixa', 'checkin_por', 'status_agendamento', 'convenio'):
        for val in filtros.get(chave) or []:
            if val:
                pares.append((chave, str(val)))
    if filtros.get('checkin'):
        pares.append(('checkin', str(filtros['checkin'])))
    if filtros.get('hora_inicial'):
        pares.append(('hora_inicial', str(filtros['hora_inicial'])))
    if filtros.get('hora_final'):
        pares.append(('hora_final', str(filtros['hora_final'])))
    if filtros.get('paciente'):
        pares.append(('paciente', str(filtros['paciente'])))
    if filtros.get('somente_marcados'):
        pares.append(('somente_marcados', '1'))
    return urlencode(pares)


def montar_regua_dias_acerto(filtros: dict, data_inicio: date, data_fim: date) -> dict:
    """Régua horizontal: mês anterior | dias do mês | mês seguinte."""
    ref = data_inicio
    y, m = ref.year, ref.month
    if data_fim.year == data_inicio.year and data_fim.month == data_inicio.month:
        ref = data_inicio
        y, m = ref.year, ref.month
    elif data_fim < data_inicio:
        y, m = data_fim.year, data_fim.month
    primeiro = date(y, m, 1)
    ultimo = _ultimo_dia_mes(primeiro)

    dia_antes = primeiro - timedelta(days=1)
    mes_ant_ini = date(dia_antes.year, dia_antes.month, 1)
    mes_ant_fim = _ultimo_dia_mes(mes_ant_ini)

    mes_seg_ini = ultimo + timedelta(days=1)
    mes_seg_fim = _ultimo_dia_mes(mes_seg_ini)

    dias = []
    for num in range(1, ultimo.day + 1):
        dia = date(y, m, num)
        dias.append(
            {
                'numero': num,
                'iso': dia.isoformat(),
                'dia_semana': DIAS_SEMANA_CURTO[dia.weekday()],
                'ativo_dia': data_inicio == data_fim == dia,
                'no_intervalo': data_inicio <= dia <= data_fim,
                'fim_semana': dia.weekday() >= 5,
                'url_query': url_query_acerto_caixa(filtros, dia, dia),
            }
        )

    titulo_mes = MESES_REGUA_PT[m] if 1 <= m <= 12 else str(m)
    ano_ant = y - 1
    ano_seg = y + 1
    return {
        'regua_titulo': f'{titulo_mes} {y}',
        'regua_ano': y,
        'regua_url_mes_anterior': url_query_acerto_caixa(filtros, mes_ant_ini, mes_ant_fim),
        'regua_url_mes_seguinte': url_query_acerto_caixa(filtros, mes_seg_ini, mes_seg_fim),
        'regua_url_ano_anterior': url_query_acerto_caixa(
            filtros, date(ano_ant, 1, 1), _ultimo_dia_mes(date(ano_ant, 12, 1))
        ),
        'regua_url_ano_seguinte': url_query_acerto_caixa(
            filtros, date(ano_seg, 1, 1), _ultimo_dia_mes(date(ano_seg, 12, 1))
        ),
        'regua_botoes_meses': _botoes_meses_ano(filtros, data_inicio, data_fim, y),
        'regua_botoes_anos': _botoes_anos(filtros, data_inicio, data_fim, y),
        'regua_dias': dias,
    }


def _parse_hora_minutos(valor) -> int | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if len(texto) <= 5 and ':' in texto:
        partes = texto.split(':')
    else:
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


def _filtrar_status(qs, status_sel: list[str]):
    if not status_sel:
        return qs.exclude(_q_status_cancelados())
    q_status = Q()
    for status in status_sel:
        if status == 'Não informado':
            q_status |= Q(status_agendamento__isnull=True) | Q(status_agendamento='')
        else:
            q_status |= Q(status_agendamento__iexact=status)
    return qs.filter(q_status) if q_status else qs


def _operadores_checkin_filtro(filtros: dict) -> list[str]:
    """Operadores selecionados (lista) ou legado `checkin` (texto parcial)."""
    raw = filtros.get('checkin_por')
    if isinstance(raw, list):
        ops = [str(x).strip() for x in raw if str(x).strip()]
        if ops:
            return ops
    leg = (filtros.get('checkin') or '').strip()
    return [leg] if leg else []


def _filtrar_checkin_por(qs, operadores: list[str], *, legado_parcial: str = ''):
    if operadores:
        return qs.filter(checkin_por__in=operadores)
    texto = (legado_parcial or '').strip()
    if texto:
        return qs.filter(checkin_por__icontains=texto)
    return qs


def _faturamento_passa_filtro_checkin(fat: FaturamentoMedico, filtros: dict) -> bool:
    operadores = _operadores_checkin_filtro(filtros)
    if operadores:
        nome = (fat.checkin_por or '').strip()
        return any(op.lower() == nome.lower() for op in operadores)
    leg = (filtros.get('checkin') or '').strip()
    if leg:
        return leg.lower() in (fat.checkin_por or '').lower()
    return True


def _badge_status(status):
    texto = (status or '').strip() or '-'
    norm = (
        texto.lower()
        .replace('ê', 'e')
        .replace('é', 'e')
        .replace('ç', 'c')
        .replace('ã', 'a')
    )
    if 'conclu' in norm or 'realiz' in norm:
        css = 'success'
    elif 'confirm' in norm:
        css = 'primary'
    elif 'aguard' in norm or 'pend' in norm or 'andamento' in norm:
        css = 'warning'
    elif norm in {'cancelado', 'desistencia', 'deletado', 'delecao'}:
        css = 'danger'
    else:
        css = 'secondary'
    return texto, css


def _moeda_br(valor) -> str:
    if valor is None:
        return '-'
    try:
        v = Decimal(str(valor))
    except Exception:
        return '-'
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _eh_aguardando_faturamento(status_txt: str) -> bool:
    s = (status_txt or '').lower()
    return 'aguard' in s and 'fatur' in s


def _item_conferencia_pendente(item: ItemServico) -> bool:
    status = (item.status_conferencia or '').strip() or 'PENDENTE'
    if item.conferido and status != 'LOTE OK':
        return False
    return status == 'PENDENTE'


def _faturamentos_escopo_fechamento_caixa(
    empresa_id: int,
    caixa: str,
    data_inicio: date,
    data_fim: date,
    filtros_snap: dict,
):
    status_sel = list(filtros_snap.get('status_agendamento') or [])
    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=data_inicio,
            data__lte=data_fim,
            caixa_acerto=caixa,
        )
        .prefetch_related('itens_servico')
        .order_by('pk')
    )
    qs = _filtrar_status(qs, status_sel)
    qs = _filtrar_checkin_por(
        qs,
        _operadores_checkin_filtro(filtros_snap),
        legado_parcial=(filtros_snap.get('checkin') or '').strip()
        if not filtros_snap.get('checkin_por')
        else '',
    )
    if filtros_snap.get('somente_marcados'):
        qs = qs.filter(marcado_acerto_caixa=True)
    return qs


def conferir_itens_pendentes_ao_fechar_caixa(
    request,
    *,
    empresa_id: int,
    caixa: str,
    data_inicio: date,
    data_fim: date,
    filtros_snap: dict,
) -> int:
    """
    Ao fechar o caixa: itens com conferência PENDENTE passam a CONFERIDO,
    exceto quando o status de agendamento é Aguardando faturamento (convênio).
    """
    hora_ini_min = _parse_hora_minutos(filtros_snap.get('hora_inicial'))
    hora_fim_min = _parse_hora_minutos(filtros_snap.get('hora_final'))
    atualizados = 0
    for fat in _faturamentos_escopo_fechamento_caixa(
        empresa_id, caixa, data_inicio, data_fim, filtros_snap
    ):
        mins = _parse_hora_minutos(fat.horario_inicio or fat.horario)
        if hora_ini_min is not None and (mins is None or mins < hora_ini_min):
            continue
        if hora_fim_min is not None and (mins is None or mins > hora_fim_min):
            continue
        if _eh_aguardando_faturamento(fat.status_agendamento or ''):
            continue
        for item in fat.itens_servico.all():
            if not _item_conferencia_pendente(item):
                continue
            status_anterior = (item.status_conferencia or '').strip() or 'PENDENTE'
            item.aplicar_status_conferencia('CONFERIDO')
            status_novo = (item.status_conferencia or '').strip() or 'PENDENTE'
            if status_novo != status_anterior:
                registrar_log_status_conferencia_item(request, item, status_novo)
            atualizados += 1
    return atualizados


def _valor_contabil_linha_acerto(linha: dict) -> Decimal:
    """Valor que entra no resumo e deve bater com a coluna Valor pago da grade."""
    vp = _valor_pago_resumo_linha(linha)
    if vp > 0:
        return vp
    if linha.get('aguardando_faturamento'):
        try:
            return Decimal(str(linha.get('total_item') or 0))
        except Exception:
            return Decimal('0')
    return Decimal('0')


def _distribuir_valor_formas_pagamento(
    total: Decimal,
    pagamentos: list,
) -> list[tuple[str, Decimal]]:
    from faturamento_medico.services.pagamentos_acerto_caixa import pagamentos_para_resumo

    if total <= 0:
        return []
    pares = pagamentos_para_resumo(pagamentos) if pagamentos else []
    if not pares:
        return []
    soma = sum(v for _, v in pares)
    if soma <= 0:
        return [(pares[0][0], total)]
    out: list[tuple[str, Decimal]] = []
    acum = Decimal('0')
    for i, (chave, val) in enumerate(pares):
        if i == len(pares) - 1:
            out.append((chave, total - acum))
        else:
            parte = (total * val / soma).quantize(Decimal('0.01'))
            out.append((chave, parte))
            acum += parte
    return out


def _bucket_caixa_resumo(
    resumo_caixas: dict[str, dict],
    caixa_val: str,
    rotulo: str,
) -> dict:
    chave = (caixa_val or '').strip()
    if chave not in resumo_caixas:
        resumo_caixas[chave] = {
            'caixa': chave,
            'rotulo': rotulo,
            'pagamento': defaultdict(Decimal),
            'aguardando': defaultdict(Decimal),
        }
    return resumo_caixas[chave]


def recomputar_resumos_acerto_caixa_de_linhas(
    linhas: list[dict],
) -> tuple[dict[str, Decimal], dict[str, Decimal], dict[str, dict]]:
    """
    Soma por forma de pagamento / convênio a partir da coluna Valor pago (por item),
    agrupando formas no nível do faturamento quando há NF/pagamentos manuais.
    """
    resumo_pagamento: dict[str, Decimal] = defaultdict(Decimal)
    resumo_aguardando: dict[str, Decimal] = defaultdict(Decimal)
    resumo_caixas: dict[str, dict] = {}
    por_fat: dict[int, list[dict]] = defaultdict(list)

    for linha in linhas:
        caixa_val = (linha.get('caixa_acerto') or '').strip()
        rotulo = (
            (linha.get('caixa_exibicao') or linha.get('caixa') or 'Sem caixa definido') or ''
        ).strip()
        bucket = _bucket_caixa_resumo(resumo_caixas, caixa_val, rotulo)
        if linha.get('aguardando_faturamento'):
            val = _valor_contabil_linha_acerto(linha)
            conv = (linha.get('convenio') or '-').strip() or '-'
            resumo_aguardando[conv] += val
            bucket['aguardando'][conv] += val
        else:
            por_fat[linha['faturamento_id']].append(linha)

    for fat_linhas in por_fat.values():
        total_vp = sum(_valor_contabil_linha_acerto(l) for l in fat_linhas)
        if total_vp <= 0:
            continue
        first = fat_linhas[0]
        caixa_val = (first.get('caixa_acerto') or '').strip()
        rotulo = (
            (first.get('caixa_exibicao') or first.get('caixa') or 'Sem caixa definido') or ''
        ).strip()
        bucket = _bucket_caixa_resumo(resumo_caixas, caixa_val, rotulo)
        pags = first.get('pagamentos_acerto') or []
        if pags:
            distrib = _distribuir_valor_formas_pagamento(total_vp, pags)
        else:
            chave = _agrupar_forma_pagamento(first.get('forma_pgto') or '-')
            distrib = [(chave, total_vp)]
        for chave, val in distrib:
            resumo_pagamento[chave] += val
            bucket['pagamento'][chave] += val

    return resumo_pagamento, resumo_aguardando, resumo_caixas


def _contagem_formas_pagamento_mes(linhas: list[dict]) -> dict[str, int]:
    """Quantidade de faturamentos (NFs) por forma de pagamento no mês."""
    por_fat: dict[int, list[dict]] = defaultdict(list)
    for linha in linhas:
        if linha.get('aguardando_faturamento'):
            continue
        por_fat[linha['faturamento_id']].append(linha)
    contagem: dict[str, int] = defaultdict(int)
    for fat_linhas in por_fat.values():
        total_vp = sum(_valor_contabil_linha_acerto(l) for l in fat_linhas)
        if total_vp <= 0:
            continue
        first = fat_linhas[0]
        pags = first.get('pagamentos_acerto') or []
        if pags:
            distrib = _distribuir_valor_formas_pagamento(total_vp, pags)
            for chave, val in distrib:
                if val > 0:
                    contagem[chave] += 1
        else:
            chave = _agrupar_forma_pagamento(first.get('forma_pgto') or '-')
            contagem[chave] += 1
    return dict(contagem)


def _montar_listas_resumo_acerto(
    resumo_pagamento: dict[str, Decimal],
    resumo_aguardando_faturamento: dict[str, Decimal],
    resumo_caixas: dict[str, dict],
    empresa_id: int,
) -> tuple[list[dict], list[dict], list[dict], Decimal, Decimal, Decimal]:
    resumo_pagamento_lista = sorted(
        [
            {'rotulo': k, 'total': v, 'total_fmt': _moeda_br(v)}
            for k, v in resumo_pagamento.items()
        ],
        key=lambda x: -x['total'],
    )
    resumo_aguardando_lista = sorted(
        [
            {'convenio': k, 'total': v, 'total_fmt': _moeda_br(v)}
            for k, v in resumo_aguardando_faturamento.items()
        ],
        key=lambda x: (-x['total'], x['convenio'].lower()),
    )
    total_aguardando = sum((row['total'] for row in resumo_aguardando_lista), Decimal('0'))
    total_pagamentos_nf = sum((row['total'] for row in resumo_pagamento_lista), Decimal('0'))
    total_resumo_geral = total_pagamentos_nf + total_aguardando

    resumo_por_caixa_lista: list[dict] = []
    for chave in sorted(
        resumo_caixas.keys(),
        key=lambda k: (resumo_caixas[k]['rotulo'] or '').lower(),
    ):
        bloco = resumo_caixas[chave]
        pagamentos_caixa = sorted(
            [
                {'rotulo': rot, 'total': tot, 'total_fmt': _moeda_br(tot)}
                for rot, tot in bloco['pagamento'].items()
            ],
            key=lambda x: -x['total'],
        )
        aguardando_caixa = sorted(
            [
                {'convenio': conv, 'total': tot, 'total_fmt': _moeda_br(tot)}
                for conv, tot in bloco['aguardando'].items()
            ],
            key=lambda x: (-x['total'], x['convenio'].lower()),
        )
        total_pag_caixa = sum((r['total'] for r in pagamentos_caixa), Decimal('0'))
        total_ag_caixa = sum((r['total'] for r in aguardando_caixa), Decimal('0'))
        total_geral_caixa = total_pag_caixa + total_ag_caixa
        resumo_por_caixa_lista.append(
            {
                'caixa': bloco['caixa'],
                'rotulo': bloco['rotulo'],
                'pagamentos': pagamentos_caixa,
                'aguardando': aguardando_caixa,
                'total_pagamentos': total_pag_caixa,
                'total_pagamentos_fmt': _moeda_br(total_pag_caixa),
                'total_aguardando': total_ag_caixa,
                'total_aguardando_fmt': _moeda_br(total_ag_caixa),
                'total_geral': total_geral_caixa,
                'total_geral_fmt': _moeda_br(total_geral_caixa),
            },
        )

    resumo_por_caixa_lista = [
        grupo
        for grupo in resumo_por_caixa_lista
        if not (grupo.get('caixa') or '').strip()
        or caixa_valor_ativo_no_acerto(empresa_id, grupo['caixa'])
        or str(grupo['caixa']).strip() in CAIXAS_ACERTO_VALORES
    ]
    return (
        resumo_pagamento_lista,
        resumo_aguardando_lista,
        resumo_por_caixa_lista,
        total_aguardando,
        total_pagamentos_nf,
        total_resumo_geral,
    )


def _agrupar_forma_pagamento(forma: str) -> str:
    f = (forma or '').strip().upper()
    if not f or f == '-':
        return 'Sem NF / forma não informada'
    if 'DINHEIRO' in f:
        return 'Dinheiro'
    if 'PIX' in f:
        return 'PIX'
    if 'DEBIT' in f or 'DÉBITO' in f or 'DEBITO' in f:
        return 'Cartão de débito'
    if 'CRED' in f or 'CRÉDITO' in f or 'CREDITO' in f:
        return 'Cartão de crédito'
    return (forma or '').strip() or 'Outros'


def _primeira_nota(linhas_nota):
    if not linhas_nota:
        return None
    return linhas_nota[0]


def _filtros_para_snapshot(filtros: dict) -> dict:
    return {
        'checkin': filtros.get('checkin') or '',
        'checkin_por': list(filtros.get('checkin_por') or []),
        'caixa': list(filtros.get('caixa') or []),
        'somente_marcados': bool(filtros.get('somente_marcados')),
        'hora_inicial': filtros.get('hora_inicial') or '',
        'hora_final': filtros.get('hora_final') or '',
        'status_agendamento': list(filtros.get('status_agendamento') or []),
        'paciente': (filtros.get('paciente') or '').strip(),
        'convenio': list(filtros.get('convenio') or []),
    }


def _fechamentos_ativos_empresa(empresa_id: int):
    try:
        return AcertoCaixaFechamento.objects.filter(
            empresa_id=empresa_id,
            reaberto_em__isnull=True,
        )
    except (ProgrammingError, OperationalError):
        return AcertoCaixaFechamento.objects.none()


def _fechamento_cobre_faturamento(fech: AcertoCaixaFechamento, fat: FaturamentoMedico) -> bool:
    if fat.empresa_id != fech.empresa_id:
        return False
    if not fat.data or fat.data < fech.data_inicio or fat.data > fech.data_fim:
        return False
    caixa_fat = (fat.caixa_acerto or '').strip()
    if caixa_fat != fech.caixa:
        return False

    snap = fech.filtros or {}
    if not _faturamento_passa_filtro_checkin(fat, snap):
        return False

    if snap.get('somente_marcados') and not fat.marcado_acerto_caixa:
        return False

    status_sel = snap.get('status_agendamento') or []
    if status_sel:
        st = (fat.status_agendamento or '').strip() or 'Não informado'
        if st not in status_sel:
            return False
    else:
        st_norm = (fat.status_agendamento or '').strip()
        for cancel in STATUS_CANCELADOS:
            if st_norm.lower() == cancel.lower():
                return False

    hora_ini_min = _parse_hora_minutos(snap.get('hora_inicial'))
    hora_fim_min = _parse_hora_minutos(snap.get('hora_final'))
    mins = _parse_hora_minutos(fat.horario_inicio or fat.horario)
    if hora_ini_min is not None and (mins is None or mins < hora_ini_min):
        return False
    if hora_fim_min is not None and (mins is None or mins > hora_fim_min):
        return False

    paciente = (snap.get('paciente') or '').strip()
    if paciente and paciente.lower() not in (fat.nome or '').lower():
        return False
    convenios_snap = snap.get('convenio') or []
    if convenios_snap:
        conv = (fat.convenio or '').strip()
        if conv not in convenios_snap:
            return False
    return True


def faturamento_caixa_bloqueado(fat: FaturamentoMedico, fechamentos_ativos=None) -> bool:
    if fechamentos_ativos is None:
        fechamentos_ativos = _fechamentos_ativos_empresa(fat.empresa_id)
    for fech in fechamentos_ativos:
        if _fechamento_cobre_faturamento(fech, fat):
            return True
    return False


def _request_com_caixa_unico(request, caixa: str):
    """Copia GET do request fixando um único caixa (para saldo por fechamento)."""

    class _Req:
        pass

    qd = request.GET.copy()
    qd.setlist('caixa', [caixa])
    r = _Req()
    r.GET = qd
    return r


def _fechamento_ativo_mesmo_escopo(
    empresa_id: int,
    caixa: str,
    data_inicio: date,
    data_fim: date,
    filtros_snap: dict,
) -> AcertoCaixaFechamento | None:
    for fech in _fechamentos_ativos_empresa(empresa_id).filter(
        caixa=caixa,
        data_inicio=data_inicio,
        data_fim=data_fim,
    ):
        if (fech.filtros or {}) == filtros_snap:
            return fech
    return None


def fechar_acertos_caixa(
    request,
    empresa_id: int,
    *,
    usuario,
) -> tuple[list[AcertoCaixaFechamento], list[str]]:
    """Fecha o acerto para cada caixa selecionado no filtro. Retorna (criados, erros)."""
    ctx = montar_contexto_acerto_caixa(request, empresa_id)
    filtros = ctx['filtros']
    caixas_sel = filtros.get('caixa') or []
    erros: list[str] = []
    if not caixas_sel:
        return [], ['Selecione ao menos um caixa no filtro para fechar.']
    if request.POST.get('valores_conferidos') not in ('1', 'true', 'on', 'yes'):
        return [], ['Marque que os valores foram conferidos antes de fechar o caixa.']

    di = _parse_data_filtro(filtros['data_inicio'])
    df = _parse_data_filtro(filtros['data_fim'])
    snap = _filtros_para_snapshot(filtros)
    criados: list[AcertoCaixaFechamento] = []

    for caixa in caixas_sel:
        if _fechamento_ativo_mesmo_escopo(empresa_id, caixa, di, df, snap):
            erros.append(
                f'{rotulo_caixa_acerto(caixa, empresa_id)} já está fechado neste período e filtros.'
            )
            continue
        sub_ctx = montar_contexto_acerto_caixa(_request_com_caixa_unico(request, caixa), empresa_id)
        resumo = sub_ctx.get('resumo_pagamento') or []
        saldo = sum((row['total'] for row in resumo), Decimal('0'))
        resumo_json = [
            {'rotulo': row['rotulo'], 'total': str(row['total'])}
            for row in resumo
        ]
        with transaction.atomic():
            fech = AcertoCaixaFechamento.objects.create(
                empresa_id=empresa_id,
                caixa=caixa,
                data_inicio=di,
                data_fim=df,
                saldo_total=saldo,
                resumo_saldos=resumo_json,
                filtros=snap,
                fechado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
            )
            conferir_itens_pendentes_ao_fechar_caixa(
                request,
                empresa_id=empresa_id,
                caixa=caixa,
                data_inicio=di,
                data_fim=df,
                filtros_snap=snap,
            )
        criados.append(fech)
    return criados, erros


def reabrir_acerto_caixa(fechamento: AcertoCaixaFechamento, *, usuario) -> None:
    if not fechamento.ativo:
        raise ValueError('Este fechamento já foi reaberto.')
    fechamento.reaberto_em = timezone.now()
    fechamento.reaberto_por = usuario if getattr(usuario, 'is_authenticated', False) else None
    fechamento.save(update_fields=['reaberto_em', 'reaberto_por'])


def montar_status_fechamentos_caixa(
    empresa_id: int,
    filtros: dict,
) -> list[dict]:
    caixas_sel = filtros.get('caixa') or []
    if not caixas_sel:
        return []
    di = _parse_data_filtro(filtros['data_inicio'])
    df = _parse_data_filtro(filtros['data_fim'])
    snap = _filtros_para_snapshot(filtros)
    status_list = []
    for caixa in caixas_sel:
        fech = _fechamento_ativo_mesmo_escopo(empresa_id, caixa, di, df, snap)
        row = {
            'caixa': caixa,
            'rotulo': rotulo_caixa_acerto(caixa, empresa_id),
            'fechado': fech is not None,
            'fechamento_id': fech.pk if fech else None,
            'fechado_em_fmt': (
                timezone.localtime(fech.fechado_em).strftime('%d/%m/%Y %H:%M')
                if fech else ''
            ),
            'saldo_total_fmt': _moeda_br(fech.saldo_total) if fech else '',
        }
        status_list.append(row)
    return status_list


def _caixa_linha_ativo_no_acerto(empresa_id: int, caixa_val: str) -> bool:
    chave = (caixa_val or '').strip()
    if not chave:
        return True
    return (
        caixa_valor_ativo_no_acerto(empresa_id, chave)
        or chave in CAIXAS_ACERTO_VALORES
    )


def _linha_status_cancelado(linha: dict) -> bool:
    st = (linha.get('status_agendamento') or '').strip()
    if not st or st == '-':
        return False
    st_low = st.lower()
    return any(st_low == cancel.lower() for cancel in STATUS_CANCELADOS)


def filtrar_linhas_acerto_caixa(
    linhas: list[dict],
    empresa_id: int,
    filtros: dict,
) -> list[dict]:
    """Mesmas regras do queryset + grade (caixa ativo, GET do formulário)."""
    caixas_sel = [str(c).strip() for c in (filtros.get('caixa') or []) if str(c).strip()]
    status_sel = list(filtros.get('status_agendamento') or [])
    somente_marcados = bool(filtros.get('somente_marcados'))
    operadores = _operadores_checkin_filtro(filtros)
    checkin_legado = (filtros.get('checkin') or '').strip()
    hora_ini = _parse_hora_minutos(filtros.get('hora_inicial'))
    hora_fim = _parse_hora_minutos(filtros.get('hora_final'))

    filtradas: list[dict] = []
    for linha in linhas:
        caixa_val = (linha.get('caixa_acerto') or '').strip()
        if caixa_val and not _caixa_linha_ativo_no_acerto(empresa_id, caixa_val):
            continue
        if caixas_sel and caixa_val not in caixas_sel:
            continue
        if somente_marcados and not linha.get('marcado_acerto_caixa'):
            continue
        if operadores:
            nome = (linha.get('checkin_por') or '').strip()
            if not any(op.lower() == nome.lower() for op in operadores):
                continue
        elif checkin_legado:
            if checkin_legado.lower() not in (linha.get('checkin_por') or '').lower():
                continue
        st = (linha.get('status_agendamento') or '').strip()
        if status_sel:
            st_cmp = st if st else 'Não informado'
            if st_cmp not in status_sel:
                continue
        elif _linha_status_cancelado(linha):
            continue
        mins = _parse_hora_minutos(linha.get('horario_inicio'))
        if hora_ini is not None and (mins is None or mins < hora_ini):
            continue
        if hora_fim is not None and (mins is None or mins > hora_fim):
            continue
        paciente = (filtros.get('paciente') or '').strip()
        if paciente and paciente.lower() not in (linha.get('paciente') or '').lower():
            continue
        convenios_sel = list(filtros.get('convenio') or [])
        if convenios_sel:
            conv = (linha.get('convenio') or '').strip()
            if conv not in convenios_sel:
                continue
        filtradas.append(linha)
    return filtradas


def montar_resumo_filtros_acerto(filtros: dict, data_inicio: date, data_fim: date) -> str:
    """Texto curto para o cabeçalho retrátil dos filtros."""
    partes = [f'{data_inicio.strftime("%d/%m/%Y")}–{data_fim.strftime("%d/%m/%Y")}']
    caixas = filtros.get('caixa') or []
    if caixas:
        partes.append(f'{len(caixas)} caixa(s)')
    checkins = filtros.get('checkin_por') or []
    if checkins:
        partes.append(f'{len(checkins)} check-in')
    status = filtros.get('status_agendamento') or []
    if status:
        partes.append(f'{len(status)} status')
    convenios = filtros.get('convenio') or []
    if convenios:
        partes.append(f'{len(convenios)} convênio(s)')
    paciente = (filtros.get('paciente') or '').strip()
    if paciente:
        partes.append(f'paciente «{paciente[:24]}{"…" if len(paciente) > 24 else ""}»')
    if filtros.get('hora_inicial') or filtros.get('hora_final'):
        hi = filtros.get('hora_inicial') or '…'
        hf = filtros.get('hora_final') or '…'
        partes.append(f'hora {hi}–{hf}')
    if filtros.get('somente_marcados'):
        partes.append('só marcados')
    return ' · '.join(partes)


def _valor_pago_resumo_linha(linha: dict) -> Decimal:
    """Mesma base da coluna «Valor pago» da grade (— na tela = 0 no total)."""
    vp = linha.get('valor_pago')
    if vp is None:
        return Decimal('0')
    try:
        return Decimal(str(vp))
    except Exception:
        return Decimal('0')


def montar_resumo_modalidades_acerto(
    linhas: list[dict],
    *,
    empresa_id: int | None = None,
    filtros: dict | None = None,
) -> dict:
    """Quantidade por modalidade; totais e gráfico usam valor pago (coluna da grade)."""
    if empresa_id is not None and filtros is not None:
        linhas = filtrar_linhas_acerto_caixa(linhas, empresa_id, filtros)
    contagem = {codigo: 0 for codigo, _ in MODALIDADES_RESUMO_ACERTO}
    valor_por_codigo = {codigo: Decimal('0') for codigo, _ in MODALIDADES_RESUMO_ACERTO}
    valor_total = Decimal('0')
    outros_qtd = 0
    outros_valor = Decimal('0')
    detalhe_fora: dict[str, dict] = {}

    for linha in linhas:
        val_item = _valor_pago_resumo_linha(linha)
        valor_total += val_item

        codigo_mod = _codigo_modalidade_para_resumo_acerto(linha)
        if codigo_mod in contagem:
            contagem[codigo_mod] += 1
            valor_por_codigo[codigo_mod] += val_item
            continue

        outros_qtd += 1
        outros_valor += val_item
        chave = codigo_mod or '-'
        if chave not in detalhe_fora:
            detalhe_fora[chave] = {'codigo': chave, 'quantidade': 0, 'valor': Decimal('0')}
        detalhe_fora[chave]['quantidade'] += 1
        detalhe_fora[chave]['valor'] += val_item

    resumo_modalidades = [
        {
            'codigo': codigo,
            'label': label,
            'quantidade': contagem[codigo],
            'valor': valor_por_codigo[codigo],
            'valor_fmt': _moeda_br(valor_por_codigo[codigo]),
        }
        for codigo, label in MODALIDADES_RESUMO_ACERTO
    ]
    if outros_qtd:
        resumo_modalidades.append(
            {
                'codigo': 'OUTROS',
                'label': 'QUANTIDADE OUTRAS MODALIDADES',
                'quantidade': outros_qtd,
                'valor': outros_valor,
                'valor_fmt': _moeda_br(outros_valor),
            }
        )

    modalidades_fora_resumo = sorted(
        detalhe_fora.values(),
        key=lambda x: (-x['valor'], x['codigo']),
    )
    for item in modalidades_fora_resumo:
        item['valor_fmt'] = _moeda_br(item['valor'])

    grafico_modalidades = [
        m for m in resumo_modalidades
        if (m.get('valor') or Decimal('0')) > 0 or m['quantidade'] > 0
    ]
    return {
        'resumo_modalidades': resumo_modalidades,
        'resumo_quantidade_total': len(linhas),
        'resumo_valor_total_fmt': _moeda_br(valor_total),
        'resumo_outros_quantidade': outros_qtd,
        'resumo_outros_valor_fmt': _moeda_br(outros_valor) if outros_qtd else '',
        'modalidades_fora_resumo': modalidades_fora_resumo,
        'grafico_modalidade_labels': [
            MODALIDADES_LABEL_CURTO_ACERTO.get(m['codigo'], m['codigo'])
            for m in grafico_modalidades
        ],
        'grafico_modalidade_valores': [float(m['valor']) for m in grafico_modalidades],
    }


def montar_resumo_viabilidade_acerto(linhas: list[dict]) -> list[dict]:
    """Agrupa por convênio/viabilidade (coluna da grade): quantidade e valor pago."""
    agreg: dict[str, dict] = {}
    for linha in linhas:
        chave = (linha.get('convenio') or '').strip() or 'Não informado'
        if chave not in agreg:
            agreg[chave] = {'quantidade': 0, 'valor': Decimal('0')}
        agreg[chave]['quantidade'] += 1
        agreg[chave]['valor'] += _valor_contabil_linha_acerto(linha)
    return sorted(
        [
            {
                'viabilidade': nome,
                'quantidade': dados['quantidade'],
                'valor': dados['valor'],
                'valor_fmt': _moeda_br(dados['valor']),
            }
            for nome, dados in agreg.items()
        ],
        key=lambda x: (-x['valor'], x['viabilidade'].lower()),
    )


def montar_resumo_viabilidade_por_mes_acerto(
    linhas: list[dict], ano: int
) -> list[dict]:
    """Janeiro a dezembro do ano: viabilidade (qt · valor pago) em cada mês."""
    por_mes: dict[int, list[dict]] = {m: [] for m in range(1, 13)}
    for linha in linhas:
        iso = (linha.get('data_iso') or '').strip()
        if len(iso) < 7:
            continue
        try:
            y = int(iso[:4])
            m = int(iso[5:7])
        except (TypeError, ValueError):
            continue
        if y != ano or m not in por_mes:
            continue
        por_mes[m].append(linha)

    blocos: list[dict] = []
    for mes in range(1, 13):
        sub = por_mes[mes]
        viabs = montar_resumo_viabilidade_acerto(sub) if sub else []
        total_qt = sum(v['quantidade'] for v in viabs)
        total_valor = sum((v['valor'] for v in viabs), Decimal('0'))
        blocos.append(
            {
                'mes': mes,
                'label': MESES_REGUA_PT[mes],
                'label_curto': MESES_BOTAO_CURTO[mes],
                'tem_dados': bool(sub),
                'total_qt': total_qt,
                'total_valor_fmt': _moeda_br(total_valor),
                'viabilidades': viabs,
            }
        )
    return blocos


def periodo_eh_ano_inteiro(data_inicio: date, data_fim: date) -> bool:
    if data_inicio.year != data_fim.year:
        return False
    ano = data_inicio.year
    return data_inicio == date(ano, 1, 1) and data_fim == _ultimo_dia_mes(date(ano, 12, 1))


def _filtrar_linhas_mes_ano(linhas: list[dict], ano: int, mes: int) -> list[dict]:
    prefixo = f'{ano}-{mes:02d}'
    return [
        linha
        for linha in linhas
        if (linha.get('data_iso') or '').strip().startswith(prefixo)
    ]


def montar_colunas_meses_resumo() -> list[dict]:
    return [
        {
            'mes': mes,
            'label_curto': MESES_BOTAO_CURTO[mes],
            'label': MESES_REGUA_PT[mes],
        }
        for mes in range(1, 13)
    ]


def montar_resumo_modalidades_matriz_mes(linhas: list[dict], ano: int) -> dict:
    """Linhas = modalidades; colunas = Jan–Dez (qt · valor pago)."""
    ctx_por_mes = [
        montar_resumo_modalidades_acerto(_filtrar_linhas_mes_ano(linhas, ano, mes))
        for mes in range(1, 13)
    ]
    codigos_ordem: list[tuple[str, str]] = list(MODALIDADES_RESUMO_ACERTO)
    if any(ctx['resumo_outros_quantidade'] for ctx in ctx_por_mes):
        codigos_ordem.append(('OUTROS', 'QUANTIDADE OUTRAS MODALIDADES'))

    linhas_matriz: list[dict] = []
    for codigo, label in codigos_ordem:
        meses_cel: list[dict] = []
        total_qt = 0
        total_valor = Decimal('0')
        for ctx in ctx_por_mes:
            item = next(
                (m for m in ctx['resumo_modalidades'] if m['codigo'] == codigo),
                None,
            )
            if item:
                qt = item['quantidade']
                val = item['valor']
                vf = item['valor_fmt']
            else:
                qt = 0
                val = Decimal('0')
                vf = _moeda_br(Decimal('0'))
            meses_cel.append({'qt': qt, 'valor_fmt': vf})
            total_qt += qt
            total_valor += val
        linhas_matriz.append(
            {
                'codigo': codigo,
                'label': label,
                'meses': meses_cel,
                'total_qt': total_qt,
                'total_valor_fmt': _moeda_br(total_valor),
            }
        )

    totais_mes = []
    for mes in range(1, 13):
        sub = _filtrar_linhas_mes_ano(linhas, ano, mes)
        valor_mes = sum((_valor_contabil_linha_acerto(l) for l in sub), Decimal('0'))
        totais_mes.append(
            {
                'qt': len(sub),
                'valor': valor_mes,
                'valor_fmt': _moeda_br(valor_mes),
            }
        )
    return {
        'modalidades_matriz_linhas': linhas_matriz,
        'modalidades_matriz_totais_mes': totais_mes,
    }


def montar_resumo_pagamento_matriz_mes(linhas: list[dict], ano: int) -> dict:
    """Formas de pagamento e aguardando faturamento por mês (qt · valor)."""
    pag_por_mes: list[dict[str, Decimal]] = []
    aguard_por_mes: list[dict[str, Decimal]] = []
    pag_qt_por_mes: list[dict[str, int]] = []
    aguard_qt_por_mes: list[dict[str, int]] = []

    for mes in range(1, 13):
        sub = _filtrar_linhas_mes_ano(linhas, ano, mes)
        pag, aguard, _ = recomputar_resumos_acerto_caixa_de_linhas(sub)
        pag_por_mes.append(dict(pag))
        aguard_por_mes.append(dict(aguard))
        pag_qt_por_mes.append(_contagem_formas_pagamento_mes(sub))
        aguard_qt: dict[str, int] = defaultdict(int)
        for linha in sub:
            if not linha.get('aguardando_faturamento'):
                continue
            conv = (linha.get('convenio') or '-').strip() or '-'
            aguard_qt[conv] += 1
        aguard_qt_por_mes.append(dict(aguard_qt))

    pag_keys = sorted(
        {k for d in pag_por_mes for k in d},
        key=lambda k: -sum(d.get(k, Decimal('0')) for d in pag_por_mes),
    )
    aguard_keys = sorted(
        {k for d in aguard_por_mes for k in d},
        key=lambda k: (
            -sum(d.get(k, Decimal('0')) for d in aguard_por_mes),
            k.lower(),
        ),
    )

    def _celulas_mes(
        keys: list[str],
        valores: list[dict[str, Decimal]],
        contagens: list[dict[str, int]],
    ) -> list[dict]:
        out: list[dict] = []
        for chave in keys:
            meses_cel: list[dict] = []
            total_qt = 0
            total_valor = Decimal('0')
            for i in range(12):
                val = valores[i].get(chave, Decimal('0'))
                qt = contagens[i].get(chave, 0)
                meses_cel.append(
                    {
                        'qt': qt,
                        'valor_fmt': _moeda_br(val) if val else _moeda_br(Decimal('0')),
                    }
                )
                total_qt += qt
                total_valor += val
            out.append(
                {
                    'rotulo': chave,
                    'meses': meses_cel,
                    'total_qt': total_qt,
                    'total_valor_fmt': _moeda_br(total_valor),
                }
            )
        return out

    totais_mes: list[dict] = []
    for i in range(12):
        pag_t = sum(pag_por_mes[i].values(), Decimal('0'))
        ag_t = sum(aguard_por_mes[i].values(), Decimal('0'))
        total_mes = pag_t + ag_t
        totais_mes.append(
            {
                'valor': total_mes,
                'valor_fmt': _moeda_br(total_mes),
                'pagamento_fmt': _moeda_br(pag_t),
                'aguardando_fmt': _moeda_br(ag_t),
            }
        )

    return {
        'pagamento_matriz_formas': _celulas_mes(pag_keys, pag_por_mes, pag_qt_por_mes),
        'pagamento_matriz_aguardando': _celulas_mes(
            aguard_keys, aguard_por_mes, aguard_qt_por_mes
        ),
        'pagamento_matriz_totais_mes': totais_mes,
    }


def montar_graficos_resumo_acerto_caixa(
    resumo_pagamento_lista: list[dict],
    total_aguardando: Decimal,
    *,
    grafico_modalidade_labels: list,
    grafico_modalidade_valores: list,
    matriz_anual: bool = False,
    meses_colunas: list[dict] | None = None,
    modalidades_totais_mes: list[dict] | None = None,
    pagamento_totais_mes: list[dict] | None = None,
) -> dict:
    pag_labels = [r['rotulo'] for r in resumo_pagamento_lista]
    pag_valores = [float(r['total']) for r in resumo_pagamento_lista]
    if total_aguardando > 0:
        pag_labels.append('Aguardando faturamento')
        pag_valores.append(float(total_aguardando))

    ctx: dict = {
        'grafico_pagamento_labels': pag_labels,
        'grafico_pagamento_valores': pag_valores,
        'grafico_torre_modalidade_labels': list(grafico_modalidade_labels),
        'grafico_torre_modalidade_valores': list(grafico_modalidade_valores),
        'grafico_torre_usar_meses': False,
        'grafico_torre_meses_labels': [],
        'grafico_torre_meses_modalidade_valores': [],
        'grafico_torre_meses_pagamento_valores': [],
    }
    if (
        matriz_anual
        and meses_colunas
        and modalidades_totais_mes
        and pagamento_totais_mes
    ):
        ctx['grafico_torre_usar_meses'] = True
        ctx['grafico_torre_meses_labels'] = [c['label_curto'] for c in meses_colunas]
        ctx['grafico_torre_meses_modalidade_valores'] = [
            float(t.get('valor') or 0) for t in modalidades_totais_mes
        ]
        ctx['grafico_torre_meses_pagamento_valores'] = [
            float(t.get('valor') or 0) for t in pagamento_totais_mes
        ]
    return ctx


def montar_contexto_matriz_anual_acerto(linhas: list[dict], di: date, df: date) -> dict:
    if not periodo_eh_ano_inteiro(di, df):
        return {'resumo_matriz_anual': False}
    ano = di.year
    return {
        'resumo_matriz_anual': True,
        'resumo_matriz_ano': ano,
        'resumo_meses_colunas': montar_colunas_meses_resumo(),
        **montar_resumo_modalidades_matriz_mes(linhas, ano),
        **montar_resumo_pagamento_matriz_mes(linhas, ano),
    }


def montar_blocos_impressao_acerto_caixa(
    linhas: list[dict],
    resumo_por_caixa: list[dict],
) -> list[dict]:
    """Agrupa linhas e resumos por caixa para impressão (sem total geral agregado)."""
    por_caixa: dict[str, list[dict]] = defaultdict(list)
    for linha in linhas:
        chave = (linha.get('caixa_acerto') or '').strip()
        por_caixa[chave].append(linha)

    blocos: list[dict] = []
    vistos: set[str] = set()
    for grupo in resumo_por_caixa:
        chave = grupo['caixa']
        vistos.add(chave)
        linhas_caixa = por_caixa.get(chave, [])
        blocos.append(
            {
                'rotulo': grupo['rotulo'],
                'caixa': chave,
                'linhas': linhas_caixa,
                'resumo': grupo,
                'quantidade_linhas': len(linhas_caixa),
            },
        )

    for chave in sorted(
        por_caixa.keys(),
        key=lambda k: (
            (por_caixa[k][0].get('caixa_exibicao') or '').lower() if por_caixa[k] else k.lower()
        ),
    ):
        if chave in vistos:
            continue
        linhas_caixa = por_caixa[chave]
        rotulo = (linhas_caixa[0].get('caixa_exibicao') if linhas_caixa else '') or 'Sem caixa definido'
        blocos.append(
            {
                'rotulo': rotulo,
                'caixa': chave,
                'linhas': linhas_caixa,
                'resumo': None,
                'quantidade_linhas': len(linhas_caixa),
            },
        )
    return blocos


def montar_contexto_acerto_caixa(request, empresa_id: int) -> dict:
    hoje = date.today()
    di_padrao, df_padrao = _periodo_padrao(hoje)
    di = _parse_data_filtro(request.GET.get('data_inicio')) or di_padrao
    df = _parse_data_filtro(request.GET.get('data_fim')) or df_padrao
    if di > df:
        di, df = df, di

    checkin_por_sel = [
        s.strip() for s in request.GET.getlist('checkin_por') if s and str(s).strip()
    ]
    checkin = (request.GET.get('checkin') or '').strip()
    valores_caixa_ativos = caixas_acerto_valores(empresa_id)
    valores_caixa = valores_caixa_ativos | CAIXAS_ACERTO_VALORES
    caixas_sel = [
        c.strip()
        for c in request.GET.getlist('caixa')
        if c
        and (
            str(c).strip() in valores_caixa_ativos
            or str(c).strip() in CAIXAS_ACERTO_VALORES
        )
    ]
    somente_marcados = request.GET.get('somente_marcados') == '1'
    hora_ini_str = (request.GET.get('hora_inicial') or '').strip()
    hora_fim_str = (request.GET.get('hora_final') or '').strip()
    hora_ini_min = _parse_hora_minutos(hora_ini_str)
    hora_fim_min = _parse_hora_minutos(hora_fim_str)

    status_sel = [
        s.strip() for s in request.GET.getlist('status_agendamento') if s and str(s).strip()
    ]
    paciente_filtro = (request.GET.get('paciente') or '').strip()
    convenios_sel = [
        s.strip() for s in request.GET.getlist('convenio') if s and str(s).strip()
    ]

    qs_base = FaturamentoMedico.objects.filter(empresa_id=empresa_id)
    qs_periodo = qs_base.filter(data__gte=di, data__lte=df)

    convenios_disponiveis = sorted(
        {
            (nome or '').strip()
            for nome in qs_periodo.values_list('convenio', flat=True).distinct()
            if (nome or '').strip()
        },
        key=str.lower,
    )

    status_disponiveis = sorted(
        {
            (status or '').strip() or 'Não informado'
            for status in qs_periodo.values_list('status_agendamento', flat=True).distinct()
        },
        key=str.lower,
    )
    checkin_disponiveis = sorted(
        {
            (nome or '').strip()
            for nome in qs_periodo.values_list('checkin_por', flat=True).distinct()
            if (nome or '').strip()
        },
        key=str.lower,
    )

    qs = _filtrar_status(qs_periodo, status_sel)
    qs = _filtrar_checkin_por(
        qs,
        checkin_por_sel,
        legado_parcial=checkin if not checkin_por_sel else '',
    )
    if paciente_filtro:
        qs = qs.filter(nome__icontains=paciente_filtro)
    if convenios_sel:
        qs = qs.filter(convenio__in=convenios_sel)
    if caixas_sel:
        qs = qs.filter(caixa_acerto__in=caixas_sel)
    if somente_marcados:
        qs = qs.filter(marcado_acerto_caixa=True)

    qs = (
        qs.order_by('data', 'horario_inicio', 'nome')
        .prefetch_related('itens_servico')
        .defer('pagamentos_acerto_json')
    )
    notas_por_data = carregar_notas_por_data(empresa_id, di, df)
    fechamentos_ativos = list(_fechamentos_ativos_empresa(empresa_id))
    fats_bloqueio: dict[int, bool] = {}

    linhas = []

    for fat in qs:
        mins = _parse_hora_minutos(fat.horario_inicio or fat.horario)
        if hora_ini_min is not None and (mins is None or mins < hora_ini_min):
            continue
        if hora_fim_min is not None and (mins is None or mins > hora_fim_min):
            continue

        notas = resolver_notas_linha(
            notas_por_data,
            empresa_id,
            fat.nome or '',
            fat.data,
            fat.nota_fiscal,
        )
        nota = _primeira_nota(notas)
        from faturamento_medico.services.pagamentos_acerto_caixa import (
            pagamentos_efetivos_faturamento,
            pagamentos_manuais_faturamento,
            serializar_pagamentos_json,
            texto_forma_pgto,
        )

        pagamentos_efetivos = pagamentos_efetivos_faturamento(fat, nota)
        forma_pgto = texto_forma_pgto(pagamentos_efetivos)
        pagamentos_nf = (nota.get('pagamentos_detalhados') or []) if nota else []
        valor_nota = None
        if nota:
            valor_nota = nota.get('valor_liquido') or nota.get('valor_bruto')
        discriminacao = (nota.get('discriminacao') or '') if nota else ''
        numero_nf = (nota.get('numero') or fat.nota_fiscal or '') if nota else (fat.nota_fiscal or '')

        status_txt, status_css = _badge_status(fat.status_agendamento)
        convenio = (fat.convenio or '-').strip() or '-'

        itens = list(fat.itens_servico.all())
        primeira_linha_faturamento = True
        data_iso = fat.data.isoformat() if fat.data else ''
        qtd_notas = len(notas)
        notas_json = notas_linha_para_json(notas) if qtd_notas > 1 else ''

        def _add_linha(item=None):
            nonlocal primeira_linha_faturamento
            if item:
                procedimento = item.servico or '-'
                codigo = item.codigo_servico or fat.codigo_servico or '-'
                modalidade = _modalidade_item(fat, item) or '-'
                com_contraste = item.com_contraste
                total_item = item.total if item.total is not None else (item.valor or 0)
                valor_tabela = item.valor or 0
                valor_pago = valor_pago_para_exibicao(item)
            else:
                procedimento = fat.servico or '-'
                codigo = fat.codigo_servico or '-'
                modalidade = _modalidade_item(fat) or '-'
                com_contraste = False
                total_item = fat.total or 0
                valor_tabela = fat.valor or 0
                valor_pago = None

            aguardando_faturamento = _eh_aguardando_faturamento(status_txt)

            caixa_valor = (fat.caixa_acerto or '').strip()
            if caixa_valor and not _caixa_linha_ativo_no_acerto(empresa_id, caixa_valor):
                return
            if caixa_valor:
                caixa_exib = rotulo_caixa_acerto(caixa_valor, empresa_id)
            else:
                caixa_exib = (fat.checkin_por or '-').strip() or '-'
            mostrar_acerto = primeira_linha_faturamento
            mostrar_nf = primeira_linha_faturamento and not aguardando_faturamento
            primeira_linha_faturamento = False

            if aguardando_faturamento:
                forma_linha = 'A FATURAR'
                valor_nota_linha = None
                valor_nota_fmt_linha = '-'
                disc_linha = '-'
            else:
                forma_linha = forma_pgto or '-'
                valor_nota_linha = valor_nota
                valor_nota_fmt_linha = _moeda_br(valor_nota) if valor_nota is not None else '-'
                disc_linha = discriminacao if discriminacao else '-'

            valor_tabela_dec = Decimal(str(valor_tabela or 0))
            if valor_nota_linha is not None:
                base_diferenca = Decimal(str(valor_nota_linha))
            else:
                base_diferenca = Decimal(str(total_item or 0))
            diferenca = base_diferenca - valor_tabela_dec

            if fat.pk not in fats_bloqueio:
                fats_bloqueio[fat.pk] = faturamento_caixa_bloqueado(fat, fechamentos_ativos)

            linhas.append({
                'faturamento_id': fat.pk,
                'data_iso': data_iso,
                'aguardando_faturamento': aguardando_faturamento,
                'caixa_bloqueado': fats_bloqueio.get(fat.pk, False),
                'marcado_acerto_caixa': bool(fat.marcado_acerto_caixa),
                'caixa_acerto': caixa_valor,
                'mostrar_acerto_celula': mostrar_acerto,
                'mostrar_nf_celula': mostrar_nf,
                'notas_vinculadas': notas,
                'qtd_notas': qtd_notas,
                'notas_json': notas_json,
                'data_fmt': fat.data.strftime('%d/%m/%Y') if fat.data else '-',
                'paciente': fat.nome or '-',
                'codigo_servico': codigo,
                'procedimento': procedimento,
                'modalidade': modalidade,
                'com_contraste': com_contraste,
                'total_item': total_item,
                'total_item_fmt': _moeda_br(total_item),
                'valor_pago': valor_pago,
                'valor_pago_fmt': _moeda_br(valor_pago) if valor_pago is not None else '',
                'valor_pago_exibir': valor_pago is not None,
                'valor_tabela': valor_tabela,
                'nota_fiscal': numero_nf or '-',
                'forma_pgto': forma_linha,
                'pagamentos_acerto_json': serializar_pagamentos_json(
                    pagamentos_manuais_faturamento(fat)
                ),
                'pagamentos_acerto': pagamentos_efetivos,
                'mostrar_forma_pgto_celula': mostrar_nf,
                'valor_nota': valor_nota_linha,
                'valor_nota_fmt': valor_nota_fmt_linha,
                'caixa': caixa_exib,
                'caixa_exibicao': caixa_exib,
                'discriminacao': disc_linha,
                'valor_tabela_fmt': _moeda_br(valor_tabela),
                'diferenca': diferenca,
                'diferenca_fmt': _moeda_br(diferenca),
                'status_agendamento': status_txt,
                'status_css': status_css,
                'convenio': convenio,
                'horario_inicio': fat.horario_inicio or fat.horario or '-',
                'horario_fim': fat.horario_fim or '-',
                'motivo_cancelamento': fat.motivo_cancelamento or '-',
                'checkin_por': fat.checkin_por or '-',
            })

        if itens:
            for item in itens:
                _add_linha(item)
        else:
            _add_linha(None)

    filtros_dict = {
        'data_inicio': di.isoformat(),
        'data_fim': df.isoformat(),
        'checkin': checkin if not checkin_por_sel else '',
        'checkin_por': checkin_por_sel,
        'caixa': caixas_sel,
        'somente_marcados': somente_marcados,
        'hora_inicial': hora_ini_str,
        'hora_final': hora_fim_str,
        'status_agendamento': status_sel,
        'paciente': paciente_filtro,
        'convenio': convenios_sel,
    }
    fechamentos_caixa = montar_status_fechamentos_caixa(empresa_id, filtros_dict)
    pode_fechar_caixa = bool(caixas_sel) and any(not row['fechado'] for row in fechamentos_caixa)
    linhas_grade = filtrar_linhas_acerto_caixa(linhas, empresa_id, filtros_dict)

    if caixas_sel:
        nome_caixa_acerto = ', '.join(rotulo_caixa_acerto(c, empresa_id) for c in caixas_sel)
    else:
        caixas_unicos = sorted(
            {
                linha.get('caixa_acerto') or ''
                for linha in linhas_grade
                if linha.get('caixa_acerto')
            },
            key=str.lower,
        )
        if caixas_unicos:
            nome_caixa_acerto = ', '.join(rotulo_caixa_acerto(c, empresa_id) for c in caixas_unicos)
        else:
            operadores = sorted(
                {
                    (linha.get('checkin_por') or '').strip()
                    for linha in linhas_grade
                    if (linha.get('checkin_por') or '').strip() and linha.get('checkin_por') != '-'
                },
                key=str.lower,
            )
            nome_caixa_acerto = ', '.join(operadores) if operadores else '—'

    (
        resumo_pagamento,
        resumo_aguardando_faturamento,
        resumo_caixas,
    ) = recomputar_resumos_acerto_caixa_de_linhas(linhas_grade)
    (
        resumo_pagamento_lista,
        resumo_aguardando_lista,
        resumo_por_caixa_lista,
        total_aguardando,
        total_pagamentos_nf,
        total_resumo_geral,
    ) = _montar_listas_resumo_acerto(
        resumo_pagamento,
        resumo_aguardando_faturamento,
        resumo_caixas,
        empresa_id,
    )
    total_valor_pago_grade = sum(
        (_valor_contabil_linha_acerto(l) for l in linhas_grade),
        Decimal('0'),
    )
    blocos_impressao = montar_blocos_impressao_acerto_caixa(
        linhas_grade,
        resumo_por_caixa_lista,
    )
    resumo_modalidades_ctx = montar_resumo_modalidades_acerto(linhas_grade)
    resumo_viabilidade = montar_resumo_viabilidade_acerto(linhas_grade)
    total_viab_qt = sum(r['quantidade'] for r in resumo_viabilidade)
    total_viab_valor = sum((r['valor'] for r in resumo_viabilidade), Decimal('0'))
    regua_ctx = montar_regua_dias_acerto(filtros_dict, di, df)
    resumo_viabilidade_por_mes = montar_resumo_viabilidade_por_mes_acerto(
        linhas_grade, regua_ctx['regua_ano']
    )
    matriz_anual_ctx = montar_contexto_matriz_anual_acerto(linhas_grade, di, df)
    graficos_resumo_ctx = montar_graficos_resumo_acerto_caixa(
        resumo_pagamento_lista,
        total_aguardando,
        grafico_modalidade_labels=resumo_modalidades_ctx.get('grafico_modalidade_labels') or [],
        grafico_modalidade_valores=resumo_modalidades_ctx.get('grafico_modalidade_valores') or [],
        matriz_anual=bool(matriz_anual_ctx.get('resumo_matriz_anual')),
        meses_colunas=matriz_anual_ctx.get('resumo_meses_colunas'),
        modalidades_totais_mes=matriz_anual_ctx.get('modalidades_matriz_totais_mes'),
        pagamento_totais_mes=matriz_anual_ctx.get('pagamento_matriz_totais_mes'),
    )

    return {
        'linhas': linhas_grade,
        'quantidade_linhas': len(linhas_grade),
        'blocos_impressao': blocos_impressao,
        'resumo_pagamento': resumo_pagamento_lista,
        'resumo_por_caixa': resumo_por_caixa_lista,
        'resumo_aguardando_faturamento': resumo_aguardando_lista,
        'total_aguardando_faturamento_fmt': _moeda_br(total_aguardando),
        'total_pagamentos_nf_fmt': _moeda_br(total_pagamentos_nf),
        'total_resumo_geral_fmt': _moeda_br(total_resumo_geral),
        'total_valor_pago_grade_fmt': _moeda_br(total_valor_pago_grade),
        'status_disponiveis': status_disponiveis,
        'checkin_disponiveis': checkin_disponiveis,
        'convenios_disponiveis': convenios_disponiveis,
        'caixas_acerto': caixas_acerto_choices(empresa_id),
        'filtros': filtros_dict,
        'filtros_resumo': montar_resumo_filtros_acerto(filtros_dict, di, df),
        **regua_ctx,
        'fechamentos_caixa': fechamentos_caixa,
        'pode_fechar_caixa': pode_fechar_caixa,
        'periodo_fmt': f'{di.strftime("%d/%m/%Y")} → {df.strftime("%d/%m/%Y")}',
        'nome_caixa_acerto': nome_caixa_acerto,
        'formas_pagamento_acerto': list(
            Cobranca.objects.all().order_by('descricao').values('id', 'descricao')
        ),
        **resumo_modalidades_ctx,
        'resumo_viabilidade': resumo_viabilidade,
        'resumo_viabilidade_total_qt': total_viab_qt,
        'resumo_viabilidade_total_valor_fmt': _moeda_br(total_viab_valor),
        'resumo_viabilidade_por_mes': resumo_viabilidade_por_mes,
        'resumo_viabilidade_por_mes_ano': regua_ctx['regua_ano'],
        **matriz_anual_ctx,
        **graficos_resumo_ctx,
    }
