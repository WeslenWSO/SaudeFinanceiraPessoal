"""Cronograma Tabela Price — taxa fixa a.m. com carência."""
from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from .sac_calculo import _juros_carencia_divididos, juros_pro_rata_mensal

TipoCarencia = Literal['juros_mensais', 'capitalizar', 'sem']


def _venc_mes(base: date, meses_a_frente: int, dia: int) -> date:
    y = base.year
    m = base.month + meses_a_frente
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    ultimo_dia = calendar.monthrange(y, m)[1]
    return date(y, m, min(dia, ultimo_dia))


def _pmt_price(pv: Decimal, taxa_juros_am: Decimal, n: int) -> Decimal:
    if n <= 0 or pv <= 0:
        return Decimal('0.00')
    i = taxa_juros_am / Decimal('100')
    if i <= 0:
        return (pv / Decimal(n)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    fator = (Decimal('1') + i) ** n
    return (pv * i * fator / (fator - Decimal('1'))).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )


def _parcela_base(
    numero: int,
    venc: date,
    valor_parcela: Decimal,
    amort: Decimal,
    juros: Decimal,
    historico: str,
) -> dict[str, Any]:
    return {
        'numero': numero,
        'data_vencimento': venc,
        'valor_parcela': valor_parcela,
        'amortizacao': amort,
        'juros': juros,
        'data_pagamento': None,
        'historico': historico,
        'valor_pago': None,
        'mora': Decimal('0'),
        'iof': Decimal('0'),
        'correcao': Decimal('0'),
        'status': 'aberta',
    }


def _gerar_price_parcelas(
    *,
    saldo: Decimal,
    taxa_juros_am: Decimal,
    n_parcelas: int,
    numero_inicio: int,
    data_ant: date,
    dia: int,
    pmt: Decimal | None = None,
    historico: str = 'Gerada Price',
    sempre_pmt_fixo: bool = False,
) -> tuple[list[dict[str, Any]], Decimal, date]:
    """Gera n parcelas Price a partir de numero_inicio."""
    if pmt is None:
        pmt = _pmt_price(saldo, taxa_juros_am, n_parcelas)

    parcelas: list[dict[str, Any]] = []
    ultimo_venc = data_ant

    for idx in range(n_parcelas):
        n = numero_inicio + idx
        venc = _venc_mes(ultimo_venc, 1, dia)
        juros = juros_pro_rata_mensal(saldo, taxa_juros_am, data_ant, venc)
        amort = (pmt - juros).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        is_ultima = idx == n_parcelas - 1
        if is_ultima and saldo > 0 and not sempre_pmt_fixo:
            amort = saldo.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            pmt_linha = (amort + juros).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif sempre_pmt_fixo and is_ultima and saldo > 0:
            amort = min(
                saldo,
                (pmt - juros).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            )
            if amort < saldo:
                juros = (pmt - amort).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                amort = saldo.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                juros = (pmt - amort).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if juros < 0:
                    juros = Decimal('0.00')
            pmt_linha = pmt
        else:
            if amort > saldo:
                amort = saldo.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            pmt_linha = pmt
            if sempre_pmt_fixo:
                juros = (pmt - amort).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if juros < 0:
                    juros = Decimal('0.00')
                    amort = min(saldo, pmt)
        saldo_fim = (saldo - amort).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if saldo_fim < 0:
            saldo_fim = Decimal('0.00')

        parcelas.append(_parcela_base(
            n, venc, pmt_linha, amort, juros, historico,
        ))
        saldo = saldo_fim
        data_ant = venc
        ultimo_venc = venc

    return parcelas, saldo, data_ant


def aplicar_pmt_fixo_parcelas(
    parcelas: list[dict[str, Any]],
    pmt: Decimal,
    *,
    de_numero: int = 1,
    ate_numero: int | None = None,
) -> None:
    """Força valor da parcela fixo e recalcula juros = PMT − amortização."""
    for p in parcelas:
        n = p['numero']
        if n < de_numero:
            continue
        if ate_numero is not None and n > ate_numero:
            continue
        if 'encargos mensais' in (p.get('historico') or ''):
            p['valor_parcela'] = pmt
            p['amortizacao'] = Decimal('0.00')
            p['juros'] = pmt
            continue
        p['valor_parcela'] = pmt
        p['juros'] = (pmt - (p['amortizacao'] or Decimal('0'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
        if p['juros'] < 0:
            p['juros'] = Decimal('0.00')


def _ajustar_ultima_amort_pmt_fixo(
    parcelas: list[dict[str, Any]],
    pmt: Decimal,
) -> None:
    """Na última parcela de amortização, limita amortização ao PMT − juros."""
    amort_linhas = [
        p for p in parcelas
        if 'encargos mensais' not in (p.get('historico') or '')
    ]
    if not amort_linhas:
        return
    ult = amort_linhas[-1]
    juros = (ult.get('juros') or Decimal('0')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    cap = (pmt - juros).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if cap > 0 and ult['amortizacao'] > cap:
        excesso = (ult['amortizacao'] - cap).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
        ult['amortizacao'] = cap
        if excesso > 0 and len(amort_linhas) >= 2:
            penult = amort_linhas[-2]
            penult['amortizacao'] = (penult['amortizacao'] + excesso).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )


def gerar_cronograma_price_com_carencia(
    *,
    valor_contrato: Decimal,
    taxa_juros_am: Decimal,
    data_operacao: date,
    n_parcelas: int,
    meses_carencia: int = 0,
    dia_vencimento: int | None = None,
    tipo_carencia: TipoCarencia = 'juros_mensais',
    pmt: Decimal | None = None,
    pmt_fixo_amort: Decimal | None = None,
) -> list[dict[str, Any]]:
    """
    Gera cronograma Price com carência.

    tipo_carencia:
      - 'juros_mensais': Caixa PEAC — carência com encargos mensais compostos
        (juros incorporados ao saldo a cada mês); depois n_parcelas Price sobre o valor original.
      - 'capitalizar': Sicoob — parcela 0, juros capitalizados, Price sobre saldo pós-carência.
      - 'sem': só Price direto (parcelas 1..n).
    """
    if valor_contrato <= 0 or n_parcelas < 1 or not data_operacao:
        return []

    tipo = tipo_carencia or 'juros_mensais'
    if meses_carencia <= 0:
        tipo = 'sem'

    dia = dia_vencimento or data_operacao.day
    if dia < 1 or dia > 31:
        dia = data_operacao.day or 1

    saldo = valor_contrato.quantize(Decimal('0.01'))
    data_ant = data_operacao
    parcelas: list[dict[str, Any]] = []

    if tipo == 'juros_mensais' and meses_carencia > 0:
        ultimo_venc = data_operacao
        i = taxa_juros_am / Decimal('100')
        saldo_carencia = saldo
        for m in range(1, meses_carencia + 1):
            venc = _venc_mes(ultimo_venc, 1, dia)
            juros = (saldo_carencia * i).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            parcelas.append(_parcela_base(
                m, venc, juros, Decimal('0.00'), juros,
                'Carência — encargos mensais',
            ))
            saldo_carencia = (saldo_carencia + juros).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )
            data_ant = venc
            ultimo_venc = venc

        pmt_amort = pmt_fixo_amort if pmt_fixo_amort is not None else pmt
        amort_parcelas, _, _ = _gerar_price_parcelas(
            saldo=saldo,
            taxa_juros_am=taxa_juros_am,
            n_parcelas=n_parcelas,
            numero_inicio=meses_carencia + 1,
            data_ant=data_ant,
            dia=dia,
            pmt=pmt_amort,
            historico='Amortização Price',
        )
        parcelas.extend(amort_parcelas)
        if pmt_fixo_amort is not None:
            _ajustar_ultima_amort_pmt_fixo(parcelas, pmt_fixo_amort)
            aplicar_pmt_fixo_parcelas(
                parcelas, pmt_fixo_amort, de_numero=meses_carencia + 1,
            )

    elif tipo == 'capitalizar' and meses_carencia > 0:
        venc_p0 = _venc_mes(data_operacao, meses_carencia, dia)
        juros_linha, _juros_cap, saldo_pos = _juros_carencia_divididos(
            saldo_inicial=saldo,
            taxa_juros_am=taxa_juros_am,
            data_inicio=data_operacao,
            vencimento_p0=venc_p0,
        )
        parcelas.append(_parcela_base(
            0, venc_p0, juros_linha, Decimal('0.00'), juros_linha, 'Carência',
        ))
        amort_parcelas, _, _ = _gerar_price_parcelas(
            saldo=saldo_pos,
            taxa_juros_am=taxa_juros_am,
            n_parcelas=n_parcelas,
            numero_inicio=1,
            data_ant=venc_p0,
            dia=dia,
        )
        parcelas.extend(amort_parcelas)

    else:
        amort_parcelas, _, _ = _gerar_price_parcelas(
            saldo=saldo,
            taxa_juros_am=taxa_juros_am,
            n_parcelas=n_parcelas,
            numero_inicio=1,
            data_ant=data_operacao,
            dia=dia,
        )
        parcelas.extend(amort_parcelas)

    return parcelas
