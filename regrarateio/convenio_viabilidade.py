"""Totais de lançamentos de rateio agrupados por viabilidade = convênio cadastrado."""
from decimal import Decimal

from django.db.models import Count, Sum

from servicos_medicos.models import Convenio


def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal('0')
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _imposto_apuracao(base: Decimal, pct: Decimal) -> Decimal:
    if base == 0 or pct <= 0:
        return Decimal('0')
    return (abs(base) * pct / Decimal('100')).quantize(Decimal('0.01'))


def coletar_totais_por_viabilidade_convenio(empresa_id, qs) -> dict:
    """
    Soma valores do queryset filtrado onde viabilidade coincide com convênio cadastrado
    (nome igual, sem diferenciar maiúsculas/minúsculas).
    """
    convenios = list(
        Convenio.objects.filter(empresa_id=empresa_id).order_by('nome')
    ) if empresa_id else []

    linhas = []
    ids_contados = set()
    total_geral = Decimal('0')
    total_impostos = Decimal('0')

    for conv in convenios:
        nome = (conv.nome or '').strip()
        if not nome:
            continue
        sub = qs.filter(viabilidade__iexact=nome)
        agg = sub.aggregate(total=Sum('valor'), qtd=Count('id'))
        total = _to_dec(agg['total'])
        qtd = int(agg['qtd'] or 0)
        if qtd == 0:
            continue
        ids_contados.update(sub.values_list('id', flat=True))

        iss = _imposto_apuracao(total, _to_dec(conv.aliquota_iss_ap))
        pis = _imposto_apuracao(total, _to_dec(conv.aliquota_pis_ap))
        cofins = _imposto_apuracao(total, _to_dec(conv.aliquota_cofins_ap))
        csll = _imposto_apuracao(total, _to_dec(conv.aliquota_csll_ap))
        irpj = _imposto_apuracao(total, _to_dec(conv.aliquota_irpj_ap))
        impostos = iss + pis + cofins + csll + irpj

        linhas.append({
            'convenio_id': conv.id,
            'viabilidade': nome,
            'qtd': qtd,
            'total': total,
            'iss_ap': iss,
            'pis_ap': pis,
            'cofins_ap': cofins,
            'csll_ap': csll,
            'irpj_ap': irpj,
            'impostos_ap': impostos,
            'liquido_ap': total - impostos if total >= 0 else total + impostos,
        })
        total_geral += total
        total_impostos += impostos

    # Viabilidade literal "CONVENIO" sem cadastro correspondente
    sub_conv = qs.filter(viabilidade__iexact='CONVENIO')
    if convenios:
        nomes = [(c.nome or '').strip().upper() for c in convenios]
        if 'CONVENIO' not in nomes:
            agg = sub_conv.aggregate(total=Sum('valor'), qtd=Count('id'))
            qtd = int(agg['qtd'] or 0)
            if qtd:
                total = _to_dec(agg['total'])
                ids_contados.update(sub_conv.values_list('id', flat=True))
                linhas.append({
                    'convenio_id': None,
                    'viabilidade': 'CONVENIO',
                    'qtd': qtd,
                    'total': total,
                    'iss_ap': Decimal('0'),
                    'pis_ap': Decimal('0'),
                    'cofins_ap': Decimal('0'),
                    'csll_ap': Decimal('0'),
                    'irpj_ap': Decimal('0'),
                    'impostos_ap': Decimal('0'),
                    'liquido_ap': total,
                    'sem_aliquota': True,
                })
                total_geral += total
    else:
        agg = sub_conv.aggregate(total=Sum('valor'), qtd=Count('id'))
        qtd = int(agg['qtd'] or 0)
        if qtd:
            total = _to_dec(agg['total'])
            ids_contados.update(sub_conv.values_list('id', flat=True))
            linhas.append({
                'convenio_id': None,
                'viabilidade': 'CONVENIO',
                'qtd': qtd,
                'total': total,
                'iss_ap': Decimal('0'),
                'pis_ap': Decimal('0'),
                'cofins_ap': Decimal('0'),
                'csll_ap': Decimal('0'),
                'irpj_ap': Decimal('0'),
                'impostos_ap': Decimal('0'),
                'liquido_ap': total,
                'sem_aliquota': True,
            })
            total_geral += total

    # Outras viabilidades no filtro que não batem com cadastro
    outros_qs = qs.exclude(viabilidade='').exclude(viabilidade__isnull=True)
    if ids_contados:
        outros_qs = outros_qs.exclude(id__in=ids_contados)

    outros_agg = outros_qs.values('viabilidade').annotate(
        total=Sum('valor'),
        qtd=Count('id'),
    ).order_by('viabilidade')

    outros = []
    for row in outros_agg:
        viab = (row['viabilidade'] or '').strip()
        if not viab:
            continue
        outros.append({
            'viabilidade': viab,
            'qtd': int(row['qtd'] or 0),
            'total': _to_dec(row['total']),
        })

    return {
        'linhas': linhas,
        'total_geral': total_geral,
        'total_impostos_ap': total_impostos,
        'outros': outros,
        'tem_convenio_cadastrado': bool(convenios),
    }
