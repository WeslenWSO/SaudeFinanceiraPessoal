"""Totais de lançamentos de rateio agrupados por viabilidade = convênio cadastrado."""
from decimal import Decimal

from django.db.models import Count, Sum

from servicos_medicos.models import Convenio

# Adicional de IRPJ (presunção 32% − limite × 15%, rateado por convênio)
AD_IRPJ_BASE_LUCRO_PCT = Decimal('32')
AD_IRPJ_ALIQUOTA_PCT = Decimal('15')
AD_IRPJ_LIMITE_MENSAL = Decimal('20000')
AD_IRPJ_LIMITE_TRIMESTRAL = Decimal('60000')


def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal('0')
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _imposto_apuracao(base: Decimal, pct: Decimal) -> Decimal:
    if base == 0 or pct <= 0:
        return Decimal('0')
    return (abs(base) * pct / Decimal('100')).quantize(Decimal('0.01'))


def _calc_ad_irpj_global(total_geral: Decimal, periodo: str = 'mensal') -> dict:
    """
    (Total × 32% − limite) × 15% = adicional IRPJ do período.
    Limite: R$ 20.000 (mensal) ou R$ 60.000 (trimestral).
    Índice = adicional ÷ total → aplicado em cada convênio.
    """
    total_abs = abs(total_geral)
    limite = (
        AD_IRPJ_LIMITE_TRIMESTRAL
        if (periodo or '').strip().lower() == 'trimestral'
        else AD_IRPJ_LIMITE_MENSAL
    )
    base_lucro = (total_abs * AD_IRPJ_BASE_LUCRO_PCT / Decimal('100')).quantize(Decimal('0.01'))
    excedente = base_lucro - limite
    if excedente <= 0:
        return {
            'periodo': periodo,
            'limite': limite,
            'base_lucro': base_lucro,
            'excedente': Decimal('0'),
            'ad_irpj_total': Decimal('0'),
            'indice': Decimal('0'),
        }
    ad_total = (excedente * AD_IRPJ_ALIQUOTA_PCT / Decimal('100')).quantize(Decimal('0.01'))
    indice = (ad_total / total_abs) if total_abs else Decimal('0')
    return {
        'periodo': periodo,
        'limite': limite,
        'base_lucro': base_lucro,
        'excedente': excedente.quantize(Decimal('0.01')),
        'ad_irpj_total': ad_total,
        'indice': indice,
    }


def _liquido_com_impostos(total: Decimal, impostos: Decimal, ad_irpj: Decimal) -> Decimal:
    if total >= 0:
        return total - impostos - ad_irpj
    return total + impostos + ad_irpj


def coletar_totais_por_viabilidade_convenio(empresa_id, qs, periodo_ad_irpj: str = 'mensal') -> dict:
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
            'ad_irpj': Decimal('0'),
            'liquido_ap': Decimal('0'),
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
                    'ad_irpj': Decimal('0'),
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
                'ad_irpj': Decimal('0'),
                'liquido_ap': total,
                'sem_aliquota': True,
            })
            total_geral += total

    ad_info = _calc_ad_irpj_global(total_geral, periodo_ad_irpj)
    indice = ad_info['indice']
    total_ad_irpj = Decimal('0')
    total_liquido = Decimal('0')
    tot_iss = tot_pis = tot_cofins = tot_csll = tot_irpj = Decimal('0')
    tot_qtd = 0
    for linha in linhas:
        total_lin = _to_dec(linha['total'])
        ad = (abs(total_lin) * indice).quantize(Decimal('0.01'))
        linha['ad_irpj'] = ad
        imp = _to_dec(linha['impostos_ap'])
        linha['total_imposto'] = imp + ad
        linha['liquido_ap'] = _liquido_com_impostos(total_lin, imp, ad)
        total_ad_irpj += ad
        total_liquido += linha['liquido_ap']
        tot_iss += _to_dec(linha['iss_ap'])
        tot_pis += _to_dec(linha['pis_ap'])
        tot_cofins += _to_dec(linha['cofins_ap'])
        tot_csll += _to_dec(linha['csll_ap'])
        tot_irpj += _to_dec(linha['irpj_ap'])
        tot_qtd += int(linha.get('qtd') or 0)

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

    total_irpj_mais_ad = tot_irpj + total_ad_irpj
    total_imposto = total_impostos + total_ad_irpj

    return {
        'linhas': linhas,
        'total_geral': total_geral,
        'total_impostos_ap': total_impostos,
        'total_ad_irpj': total_ad_irpj,
        'total_imposto': total_imposto,
        'total_liquido_ap': total_liquido,
        'total_irpj_ap': tot_irpj,
        'total_irpj_mais_ad': total_irpj_mais_ad,
        'totais_colunas': {
            'qtd': tot_qtd,
            'iss_ap': tot_iss,
            'pis_ap': tot_pis,
            'cofins_ap': tot_cofins,
            'csll_ap': tot_csll,
            'irpj_ap': tot_irpj,
        },
        'ad_irpj': ad_info,
        'outros': outros,
        'tem_convenio_cadastrado': bool(convenios),
    }
