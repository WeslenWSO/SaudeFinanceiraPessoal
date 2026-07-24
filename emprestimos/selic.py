"""
Consulta SELIC diária no Banco Central (SGS 11) e calcula fator no período.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SGS_SELIC_DIARIA = 11  # % a.d.


def _fmt_br(d: date) -> str:
    return d.strftime('%d/%m/%Y')


def fator_selic_periodo(data_inicio: date, data_fim: date) -> tuple[Decimal, str]:
    """
    Retorna (fator_acumulado, mensagem).
    Fator 1.0 = sem correção. Juros = saldo * (fator - 1).
    Usa taxas diárias do BCB entre data_inicio (exclusive) e data_fim (inclusive),
    prática comum para correção por dias úteis/corridos da série.
    """
    if data_fim <= data_inicio:
        return Decimal('1'), 'Período sem dias de correção.'

    # Margem para garantir retorno da API
    di = data_inicio - timedelta(days=5)
    url = (
        f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{SGS_SELIC_DIARIA}/dados'
        f'?formato=json&dataInicial={_fmt_br(di)}&dataFinal={_fmt_br(data_fim)}'
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        dados = resp.json()
    except Exception as exc:
        logger.warning('Falha ao consultar SELIC BCB: %s', exc)
        return Decimal('1'), f'Não foi possível obter SELIC no BCB ({exc}). Informe a taxa manualmente.'

    if not isinstance(dados, list) or not dados:
        return Decimal('1'), 'BCB não retornou taxas SELIC para o período.'

    fator = Decimal('1')
    usados = 0
    for item in dados:
        try:
            d = date(
                int(item['data'][6:10]),
                int(item['data'][3:5]),
                int(item['data'][0:2]),
            )
            # aplica taxas a partir do dia seguinte à referência até a data fim
            if d <= data_inicio or d > data_fim:
                continue
            taxa_ad = Decimal(str(item['valor']).replace(',', '.'))
            # valor SGS 11 é % a.d.
            fator *= (Decimal('1') + taxa_ad / Decimal('100'))
            usados += 1
        except Exception:
            continue

    if usados == 0:
        return Decimal('1'), 'Nenhuma taxa SELIC diária no intervalo.'

    msg = f'SELIC BCB: {usados} dia(s) de { _fmt_br(data_inicio) } a { _fmt_br(data_fim) }.'
    return fator.quantize(Decimal('0.00000001')), msg


def juros_selic_sobre_saldo(
    saldo: Decimal,
    data_inicio: date,
    data_fim: date,
    pct_correcao: Decimal = Decimal('100'),
    taxa_manual_periodo_pct: Optional[Decimal] = None,
) -> tuple[Decimal, dict]:
    """
    Calcula juros/correção SELIC sobre saldo.
    Se taxa_manual_periodo_pct for informada, usa saldo * taxa/100 * pct_correcao/100
    (taxa acumulada no período, em %). Caso contrário, consulta BCB.
    """
    saldo = saldo or Decimal('0')
    pct = pct_correcao if pct_correcao is not None else Decimal('100')
    detalhe: dict = {
        'fonte': '',
        'fator': Decimal('1'),
        'mensagem': '',
        'pct_correcao': pct,
    }

    if saldo <= 0 or data_fim <= data_inicio:
        detalhe['mensagem'] = 'Sem saldo ou período inválido.'
        return Decimal('0.00'), detalhe

    if taxa_manual_periodo_pct is not None and taxa_manual_periodo_pct != '':
        taxa = Decimal(str(taxa_manual_periodo_pct))
        juros = (saldo * (taxa / Decimal('100')) * (pct / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        detalhe.update({
            'fonte': 'manual',
            'fator': (Decimal('1') + taxa / Decimal('100') * pct / Decimal('100')),
            'mensagem': f'Taxa SELIC manual do período: {taxa}% (aplicado {pct}% da correção).',
        })
        return juros, detalhe

    fator, msg = fator_selic_periodo(data_inicio, data_fim)
    # aplica % de correção (ex.: 100% da SELIC)
    fator_efetivo = Decimal('1') + (fator - Decimal('1')) * (pct / Decimal('100'))
    juros = (saldo * (fator_efetivo - Decimal('1'))).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    detalhe.update({
        'fonte': 'bcb',
        'fator': fator_efetivo,
        'mensagem': msg,
    })
    return juros, detalhe
