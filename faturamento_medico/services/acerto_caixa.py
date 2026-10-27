"""Montagem de dados para a tela Acerto de Caixa."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from cobranca.models import Cobranca
from faturamento_medico.lote_relatorio import _modalidade_item
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
    proximo = hoje.replace(day=28) + timedelta(days=4)
    fim = proximo - timedelta(days=proximo.day)
    return ini, fim


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
    checkin = (filtros_snap.get('checkin') or '').strip()
    if checkin:
        qs = qs.filter(checkin_por__icontains=checkin)
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
        'caixa': list(filtros.get('caixa') or []),
        'somente_marcados': bool(filtros.get('somente_marcados')),
        'hora_inicial': filtros.get('hora_inicial') or '',
        'hora_final': filtros.get('hora_final') or '',
        'status_agendamento': list(filtros.get('status_agendamento') or []),
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
    checkin = (snap.get('checkin') or '').strip()
    if checkin and checkin.lower() not in (fat.checkin_por or '').lower():
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

    qs_base = FaturamentoMedico.objects.filter(empresa_id=empresa_id)
    qs_periodo = qs_base.filter(data__gte=di, data__lte=df)

    status_disponiveis = sorted(
        {
            (status or '').strip() or 'Não informado'
            for status in qs_periodo.values_list('status_agendamento', flat=True).distinct()
        },
        key=str.lower,
    )

    qs = _filtrar_status(qs_periodo, status_sel)
    if checkin:
        qs = qs.filter(checkin_por__icontains=checkin)
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
    resumo_pagamento: dict[str, Decimal] = defaultdict(Decimal)
    resumo_aguardando_faturamento: dict[str, Decimal] = defaultdict(Decimal)
    resumo_caixas: dict[str, dict] = {}

    def _bucket_caixa(caixa_val: str, rotulo: str) -> dict:
        chave = (caixa_val or '').strip()
        if chave not in resumo_caixas:
            resumo_caixas[chave] = {
                'caixa': chave,
                'rotulo': rotulo,
                'pagamento': defaultdict(Decimal),
                'aguardando': defaultdict(Decimal),
            }
        return resumo_caixas[chave]

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
            pagamentos_para_resumo,
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
        pagamento_contabilizado = False
        primeira_linha_faturamento = True
        data_iso = fat.data.isoformat() if fat.data else ''
        qtd_notas = len(notas)
        notas_json = notas_linha_para_json(notas) if qtd_notas > 1 else ''

        def _add_linha(item=None):
            nonlocal primeira_linha_faturamento
            nonlocal pagamento_contabilizado
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
            if caixa_valor:
                caixa_exib = rotulo_caixa_acerto(caixa_valor, empresa_id)
            else:
                caixa_exib = (fat.checkin_por or '-').strip() or '-'
            rotulo_bucket = caixa_exib if caixa_valor else 'Sem caixa definido'
            bucket = _bucket_caixa(caixa_valor, rotulo_bucket)

            if not pagamento_contabilizado:
                if not aguardando_faturamento:
                    pares_resumo = pagamentos_para_resumo(pagamentos_efetivos)
                    if pares_resumo:
                        for chave_pag, val_dec in pares_resumo:
                            resumo_pagamento[chave_pag] += val_dec
                            bucket['pagamento'][chave_pag] += val_dec
                    else:
                        chave_pag = _agrupar_forma_pagamento(forma_pgto)
                        if valor_nota is not None:
                            val_dec = Decimal(str(valor_nota))
                        else:
                            val_dec = Decimal(str(total_item or 0))
                        resumo_pagamento[chave_pag] += val_dec
                        bucket['pagamento'][chave_pag] += val_dec
                pagamento_contabilizado = True

            if aguardando_faturamento:
                val_ag = Decimal(str(total_item or 0))
                resumo_aguardando_faturamento[convenio] += val_ag
                bucket['aguardando'][convenio] += val_ag

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
        resumo_por_caixa_lista.append(
            {
                'caixa': bloco['caixa'],
                'rotulo': bloco['rotulo'],
                'pagamentos': pagamentos_caixa,
                'aguardando': aguardando_caixa,
                'total_pagamentos': total_pag_caixa,
                'total_pagamentos_fmt': _moeda_br(total_pag_caixa),
                'total_aguardando_fmt': _moeda_br(total_ag_caixa),
            },
        )

    resumo_por_caixa_lista = [
        grupo
        for grupo in resumo_por_caixa_lista
        if not (grupo.get('caixa') or '').strip()
        or caixa_valor_ativo_no_acerto(empresa_id, grupo['caixa'])
        or str(grupo['caixa']).strip() in CAIXAS_ACERTO_VALORES
    ]

    if caixas_sel:
        nome_caixa_acerto = ', '.join(rotulo_caixa_acerto(c, empresa_id) for c in caixas_sel)
    else:
        caixas_unicos = sorted(
            {
                linha.get('caixa_acerto') or ''
                for linha in linhas
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
                    for linha in linhas
                    if (linha.get('checkin_por') or '').strip() and linha.get('checkin_por') != '-'
                },
                key=str.lower,
            )
            nome_caixa_acerto = ', '.join(operadores) if operadores else '—'

    filtros_dict = {
        'data_inicio': di.isoformat(),
        'data_fim': df.isoformat(),
        'checkin': checkin,
        'caixa': caixas_sel,
        'somente_marcados': somente_marcados,
        'hora_inicial': hora_ini_str,
        'hora_final': hora_fim_str,
        'status_agendamento': status_sel,
    }
    fechamentos_caixa = montar_status_fechamentos_caixa(empresa_id, filtros_dict)
    pode_fechar_caixa = bool(caixas_sel) and any(not row['fechado'] for row in fechamentos_caixa)
    blocos_impressao = montar_blocos_impressao_acerto_caixa(linhas, resumo_por_caixa_lista)

    return {
        'linhas': linhas,
        'quantidade_linhas': len(linhas),
        'blocos_impressao': blocos_impressao,
        'resumo_pagamento': resumo_pagamento_lista,
        'resumo_por_caixa': resumo_por_caixa_lista,
        'resumo_aguardando_faturamento': resumo_aguardando_lista,
        'total_aguardando_faturamento_fmt': _moeda_br(total_aguardando),
        'total_pagamentos_nf_fmt': _moeda_br(total_pagamentos_nf),
        'status_disponiveis': status_disponiveis,
        'caixas_acerto': caixas_acerto_choices(empresa_id),
        'filtros': filtros_dict,
        'fechamentos_caixa': fechamentos_caixa,
        'pode_fechar_caixa': pode_fechar_caixa,
        'periodo_fmt': f'{di.strftime("%d/%m/%Y")} → {df.strftime("%d/%m/%Y")}',
        'nome_caixa_acerto': nome_caixa_acerto,
        'formas_pagamento_acerto': list(
            Cobranca.objects.all().order_by('descricao').values('id', 'descricao')
        ),
    }
