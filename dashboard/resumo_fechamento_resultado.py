"""Consultas e formatação para o relatório Resumo fechamento por resultado."""
from collections import defaultdict
from decimal import Decimal

from regrarateio.models import LancamentoRateio, _meta_observacao_importacao
from regrarateio.views import _filtra_queryset_lancamento_rateio_por_periodo

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


def _meta_observacao_car(car):
    meta = _meta_observacao_importacao((car.observacao or '') if car else '')
    return meta['modalidade'], meta['viabilidade']


def _cliente_receita_txt(lr):
    if not lr.conta_receber_id:
        return '—'
    car = lr.conta_receber
    paciente = _meta_observacao_importacao(car.observacao or '')['paciente']
    if not paciente and lr.descricao and 'Pac:' in lr.descricao:
        paciente = _meta_observacao_importacao(lr.descricao)['paciente']
    return paciente or '—'


def _textos_receita_extra(lr):
    modalidade_txt = '—'
    forma_pgto_txt = '—'
    viabilidade_txt = '—'
    if not lr.conta_receber_id:
        return modalidade_txt, forma_pgto_txt, viabilidade_txt
    car = lr.conta_receber
    mod_obs, viab_obs = _meta_observacao_car(car)
    if mod_obs:
        modalidade_txt = mod_obs
    elif car.nota_id and getattr(car.nota, 'segmento', None):
        modalidade_txt = (car.nota.segmento or '').strip() or '—'
    if car.forma_pagamento_id:
        forma_pgto_txt = car.forma_pagamento.descricao
    elif car.nota_id and car.nota.forma_pagamento_id:
        forma_pgto_txt = car.nota.forma_pagamento.descricao
    if viab_obs:
        viabilidade_txt = viab_obs
    elif car.cliente:
        viabilidade_txt = car.cliente[:80]
    return modalidade_txt, forma_pgto_txt, viabilidade_txt


def _fmt_moeda_br(d):
    if d is None:
        return '0,00'
    x = d if isinstance(d, Decimal) else Decimal(str(d))
    neg = x < 0
    a = abs(x).quantize(Decimal('0.01'))
    s = f'{a:.2f}'
    int_part, frac = s.split('.')
    if len(int_part) > 3:
        parts = []
        while int_part:
            parts.insert(0, int_part[-3:])
            int_part = int_part[:-3]
        int_part = '.'.join(parts)
    return ('-' if neg else '') + f'{int_part},{frac}'


def _grade_linhas_rateio(qs):
    out = []
    soma = Decimal('0')
    for lr in qs:
        v = lr.valor if lr.valor is not None else Decimal('0')
        soma += v
        if lr.conta_receber_id and lr.conta_receber.nota_id:
            nota_txt = lr.conta_receber.nota.numero_nota
        else:
            nota_txt = '—'
        if lr.conta_pagar_id:
            vt = lr.conta_pagar.valorDoc
        elif lr.conta_receber_id:
            vt = lr.conta_receber.valor_a_receber
        else:
            vt = Decimal('0')
        if vt is None:
            vt = Decimal('0')
        if lr.conta_pagar_id and lr.conta_pagar:
            cap = lr.conta_pagar
            emissao = cap.dtEmissao
            emissao_txt = emissao.strftime('%d/%m/%Y') if emissao else '—'
            pgto_ref = cap.dtPag or lr.data_pagamento
            data_txt = pgto_ref.strftime('%d/%m/%Y') if pgto_ref else '—'
        else:
            emissao_txt = '—'
            data_txt = (
                lr.data_pagamento.strftime('%d/%m/%Y') if lr.data_pagamento else '—'
            )
        modalidade_txt, forma_pgto_txt, viabilidade_txt = _textos_receita_extra(lr)
        cliente_txt = _cliente_receita_txt(lr) if lr.conta_receber_id else '—'
        out.append(
            {
                'data_txt': data_txt,
                'emissao_txt': emissao_txt,
                'nota_txt': nota_txt,
                'cliente_txt': cliente_txt,
                'titulo_valor_txt': _fmt_moeda_br(vt),
                'descricao': (lr.descricao or '').strip() or '—',
                'socio_nome': str(lr.socio) if lr.socio_id else '—',
                'modalidade_txt': modalidade_txt,
                'forma_pagamento_txt': forma_pgto_txt,
                'viabilidade_txt': viabilidade_txt,
                'valor_txt': _fmt_moeda_br(abs(v)),
                'valor_negativo': v < 0,
            }
        )
    return out, soma


def _iter_chaves_mes(data_inicio, data_fim):
    y, m = data_inicio.year, data_inicio.month
    yf, mf = data_fim.year, data_fim.month
    while (y, m) <= (yf, mf):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _label_mes(ano: int, mes: int) -> str:
    nome = MESES_PT[mes] if 1 <= mes <= 12 else str(mes)
    return f'{nome}/{ano}'


def parse_distribuicao_resultado(raw: str) -> list[dict]:
    """Interpreta JSON enviado pela tela (% por sócio) para exportação Excel."""
    import json

    if not (raw or '').strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        nome = (item.get('nome') or '').strip()
        if not nome:
            continue
        try:
            pct = Decimal(str(item.get('pct') or '0').replace(',', '.'))
        except Exception:
            pct = Decimal('0')
        if pct <= 0:
            continue
        out.append({'nome': nome, 'pct': pct})
    return out


def coletar_resumo_mensal_resultado(empresa_id, data_inicio, data_fim, filtro_socio_ids):
    """Totais mês a mês (receita, despesa, resultado) para todos os meses do filtro."""
    base = LancamentoRateio.objects.filter(empresa_id=empresa_id)
    qs = _filtra_queryset_lancamento_rateio_por_periodo(base, data_inicio, data_fim)
    if filtro_socio_ids:
        qs = qs.filter(socio_id__in=filtro_socio_ids)

    agg: dict[tuple[int, int], dict] = defaultdict(
        lambda: {'receita': Decimal('0'), 'deducao': Decimal('0'), 'despesa': Decimal('0')}
    )
    for lr in qs.values_list('data_pagamento', 'tipo', 'valor'):
        data_pg, tipo, valor = lr
        if not data_pg:
            continue
        chave = (data_pg.year, data_pg.month)
        v = valor if valor is not None else Decimal('0')
        if tipo == LancamentoRateio.TIPO_RECEBIMENTO:
            agg[chave]['receita'] += abs(v)
        elif tipo == LancamentoRateio.TIPO_DEDUCAO_RECEITA:
            agg[chave]['deducao'] += abs(v)
        elif tipo == LancamentoRateio.TIPO_PGTO:
            agg[chave]['despesa'] += abs(v)

    resumo = []
    for ano, mes in _iter_chaves_mes(data_inicio, data_fim):
        tot = agg.get((ano, mes), {'receita': Decimal('0'), 'deducao': Decimal('0'), 'despesa': Decimal('0')})
        receita = tot['receita']
        deducao = tot['deducao']
        despesa = tot['despesa']
        resultado = receita - deducao - despesa
        resumo.append(
            {
                'ano': ano,
                'mes': mes,
                'label': _label_mes(ano, mes),
                'receita': receita,
                'deducao': deducao,
                'despesa': despesa,
                'resultado': resultado,
                'receita_txt': _fmt_moeda_br(receita),
                'deducao_txt': _fmt_moeda_br(deducao),
                'despesa_txt': _fmt_moeda_br(despesa),
                'resultado_txt': _fmt_moeda_br(resultado),
                'resultado_negativo': resultado < 0,
            }
        )
    return resumo


def coletar_dados_resumo_resultado(empresa_id, data_inicio, data_fim, filtro_socio_ids):
    rateio_related = (
        'socio',
        'conta_pagar',
        'conta_pagar__categoria',
        'conta_receber',
        'conta_receber__forma_pagamento',
        'conta_receber__nota',
        'conta_receber__nota__forma_pagamento',
    )
    base = LancamentoRateio.objects.filter(empresa_id=empresa_id).select_related(
        *rateio_related
    )
    qs = _filtra_queryset_lancamento_rateio_por_periodo(base, data_inicio, data_fim)
    if filtro_socio_ids:
        qs = qs.filter(socio_id__in=filtro_socio_ids)

    qs_pg = (
        qs.filter(tipo=LancamentoRateio.TIPO_PGTO)
        .distinct()
        .order_by('-data_pagamento', '-id')
    )
    qs_rec = (
        qs.filter(tipo=LancamentoRateio.TIPO_RECEBIMENTO)
        .distinct()
        .order_by('-data_pagamento', '-id')
    )
    qs_ded = (
        qs.filter(tipo=LancamentoRateio.TIPO_DEDUCAO_RECEITA)
        .distinct()
        .order_by('-data_pagamento', '-id')
    )

    linhas_despesa, soma_pg = _grade_linhas_rateio(qs_pg)
    linhas_receita, soma_rec = _grade_linhas_rateio(qs_rec)
    _, soma_ded = _grade_linhas_rateio(qs_ded)

    total_despesa = abs(soma_pg)
    total_deducao = abs(soma_ded)
    total_receita = abs(soma_rec)
    resultado = soma_rec + soma_ded + soma_pg

    return {
        'linhas_despesa': linhas_despesa,
        'linhas_receita': linhas_receita,
        'total_despesa': total_despesa,
        'total_deducao': total_deducao,
        'total_receita': total_receita,
        'resultado': resultado,
        'total_despesa_txt': _fmt_moeda_br(total_despesa),
        'total_deducao_txt': _fmt_moeda_br(total_deducao),
        'total_receita_txt': _fmt_moeda_br(total_receita),
        'resultado_txt': _fmt_moeda_br(resultado),
        'resultado_negativo': resultado < 0,
    }
