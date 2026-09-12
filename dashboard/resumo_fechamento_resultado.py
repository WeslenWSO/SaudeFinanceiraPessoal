"""Consultas e formatação para o relatório Resumo fechamento por resultado."""
from decimal import Decimal

from regrarateio.models import LancamentoRateio
from regrarateio.views import _filtra_queryset_lancamento_rateio_por_periodo


def _meta_observacao_car(car):
    modalidade = ''
    viabilidade = ''
    if car and car.observacao:
        for part in car.observacao.split('|'):
            p = part.strip()
            if p.startswith('Mod:'):
                modalidade = p[4:].strip()
            elif p.startswith('Viab:'):
                viabilidade = p[5:].strip()
    return modalidade, viabilidade


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
        out.append(
            {
                'data_txt': data_txt,
                'emissao_txt': emissao_txt,
                'nota_txt': nota_txt,
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

    linhas_despesa, soma_pg = _grade_linhas_rateio(qs_pg)
    linhas_receita, soma_rec = _grade_linhas_rateio(qs_rec)

    total_despesa = abs(soma_pg)
    total_receita = abs(soma_rec)
    resultado = soma_rec + soma_pg

    return {
        'linhas_despesa': linhas_despesa,
        'linhas_receita': linhas_receita,
        'total_despesa': total_despesa,
        'total_receita': total_receita,
        'resultado': resultado,
        'total_despesa_txt': _fmt_moeda_br(total_despesa),
        'total_receita_txt': _fmt_moeda_br(total_receita),
        'resultado_txt': _fmt_moeda_br(resultado),
        'resultado_negativo': resultado < 0,
    }
