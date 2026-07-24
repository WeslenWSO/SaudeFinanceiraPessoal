"""
CDI diário no Banco Central (SGS 12) para juros SAC/SACD.

Fórmula alinhada ao extrato Sicoob:

  1) Acumula o CDI puro nos dias úteis do período:
       fator_CDI = ∏ (1 + CDI_d / 100)

  2) Aplica o % do índice sobre o retorno acumulado:
       fator_efetivo = 1 + (fator_CDI − 1) × (pct / 100)

  3) Se houver taxa prefixada a.m. (SACD, ex. 0,85%):
       fator_taxa = (1 + taxa_am/100) ^ (dias_corridos / 30)
       fator_total = fator_efetivo × fator_taxa
       J = Saldo × (fator_total − 1)
     (com taxa 0, reduz ao caso só CDI)

Período (parcelas): data_inicio < d ≤ data_fim.
Quitação: incluir_data_inicio=True → data_inicio ≤ d ≤ data_fim.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SGS_CDI_DIARIA = 12  # % a.d.


def fator_taxa_prefixada_am(
    taxa_am: Decimal | None,
    data_inicio: date,
    data_fim: date,
) -> tuple[Decimal, int]:
    """
    Fator da taxa prefixada a.m. no período (dias corridos / 30).
    Retorna (fator, dias_corridos). Fator 1 = sem acréscimo.
    """
    taxa = Decimal(str(taxa_am or 0))
    dias = max(0, (data_fim - data_inicio).days)
    if taxa <= 0 or dias <= 0:
        return Decimal('1'), dias
    i = taxa / Decimal('100')
    fator = (Decimal('1') + i) ** (Decimal(dias) / Decimal('30'))
    return fator, dias


def _fmt_br(d: date) -> str:
    return d.strftime('%d/%m/%Y')


def _parse_data_br(s: str) -> date | None:
    try:
        return date(int(s[6:10]), int(s[3:5]), int(s[0:2]))
    except Exception:
        return None


def carregar_cdi_diario(data_inicio: date, data_fim: date) -> list[tuple[date, Decimal]]:
    """Lista (data, taxa_%_a.d.) do BCB no intervalo ampliado."""
    if data_fim < data_inicio:
        return []
    # Garante histórico recente para estimar períodos futuros
    hoje = date.today()
    di = min(data_inicio, hoje) - timedelta(days=10)
    df = max(data_fim, hoje)
    # API do BCB rejeita dataFinal muito no futuro sem série — limita ao hoje+buffer
    # e deixa a estimativa completar o restante.
    df_api = min(df, hoje + timedelta(days=5))
    if df_api < di:
        df_api = hoje
    url = (
        f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{SGS_CDI_DIARIA}/dados'
        f'?formato=json&dataInicial={_fmt_br(di)}&dataFinal={_fmt_br(df_api)}'
    )
    try:
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        dados = resp.json()
    except Exception as exc:
        logger.warning('Falha ao consultar CDI BCB: %s', exc)
        raise

    out: list[tuple[date, Decimal]] = []
    if not isinstance(dados, list):
        return out
    for item in dados:
        d = _parse_data_br(str(item.get('data') or ''))
        if not d:
            continue
        try:
            taxa = Decimal(str(item['valor']).replace(',', '.'))
        except Exception:
            continue
        out.append((d, taxa))
    out.sort(key=lambda x: x[0])
    return out


def fator_cdi_periodo(
    data_inicio: date,
    data_fim: date,
    pct_indice: Decimal = Decimal('100'),
    series: list[tuple[date, Decimal]] | None = None,
    incluir_data_inicio: bool = False,
) -> tuple[Decimal, int, str]:
    """
    Retorna (fator_efetivo, dias_uteis_usados, mensagem).
    Fator 1 = sem juros. Juros = saldo * (fator - 1).

    Por padrão: data_inicio < d ≤ data_fim (parcelas).
    Quitação / saldo p/ quitação: incluir_data_inicio=True → data_inicio ≤ d ≤ data_fim.
    """
    if data_fim <= data_inicio and not incluir_data_inicio:
        return Decimal('1'), 0, 'Período sem dias de correção.'
    if data_fim < data_inicio:
        return Decimal('1'), 0, 'Período sem dias de correção.'

    pct = pct_indice if pct_indice is not None else Decimal('100')
    mult = pct / Decimal('100')  # 192 → 1.92

    try:
        dados = series if series is not None else carregar_cdi_diario(data_inicio, data_fim)
    except Exception as exc:
        return Decimal('1'), 0, f'Não foi possível obter CDI no BCB ({exc}).'

    if not dados:
        return Decimal('1'), 0, 'BCB não retornou taxas CDI para o período.'

    fator_cdi = Decimal('1')
    usados = 0
    ultima_taxa: Decimal | None = None
    ultima_data_usada: date | None = None
    for d, taxa_ad in dados:
        if incluir_data_inicio:
            if d < data_inicio or d > data_fim:
                continue
        else:
            if d <= data_inicio or d > data_fim:
                continue
        fator_cdi *= (Decimal('1') + taxa_ad / Decimal('100'))
        usados += 1
        ultima_taxa = taxa_ad
        ultima_data_usada = d

    # Completa dias úteis sem CDI publicado quando o vencimento é futuro
    # (inclui o "buraco" de hoje até o vencimento). Na quitação até hoje
    # (data_fim <= hoje) não estima — só taxas publicadas.
    estimados = 0
    hoje = date.today()
    if (
        ultima_taxa is not None
        and data_fim > hoje
        and ultima_data_usada is not None
    ):
        d = ultima_data_usada + timedelta(days=1)
        while d <= data_fim:
            if d.weekday() < 5:
                fator_cdi *= (Decimal('1') + ultima_taxa / Decimal('100'))
                estimados += 1
            d += timedelta(days=1)

    if usados == 0 and estimados == 0:
        taxa_ref = dados[-1][1] if dados else None
        if taxa_ref is None:
            return Decimal('1'), 0, 'Nenhuma taxa CDI diária no intervalo.'
        # Período totalmente futuro: estima todos os dias úteis
        if data_fim > hoje or data_inicio >= hoje:
            dias_uteis = _contar_dias_uteis(
                data_inicio, data_fim, incluir_inicio=incluir_data_inicio,
            )
            if dias_uteis <= 0:
                return Decimal('1'), 0, 'Período sem dias úteis.'
            fator_cdi = (Decimal('1') + taxa_ref / Decimal('100')) ** dias_uteis
            fator = Decimal('1') + (fator_cdi - Decimal('1')) * mult
            msg = (
                f'CDI estimado (última {taxa_ref}% a.d. × {pct}%): '
                f'{dias_uteis} dia(s) útil(is) de {_fmt_br(data_inicio)} a {_fmt_br(data_fim)}.'
            )
            return fator.quantize(Decimal('0.00000001')), dias_uteis, msg
        return Decimal('1'), 0, 'Nenhuma taxa CDI diária no intervalo.'

    if usados == 0 and estimados > 0:
        fator = Decimal('1') + (fator_cdi - Decimal('1')) * mult
        msg = (
            f'CDI estimado (última {ultima_taxa}% a.d. × {pct}%): '
            f'{estimados} dia(s) útil(is) de {_fmt_br(data_inicio)} a {_fmt_br(data_fim)}.'
        )
        return fator.quantize(Decimal('0.00000001')), estimados, msg

    total_dias = usados + estimados
    fator = Decimal('1') + (fator_cdi - Decimal('1')) * mult
    msg = (
        f'CDI BCB × {pct}% do índice: {usados} dia(s) publicado(s)'
        + (f' + {estimados} estimado(s)' if estimados else '')
        + f' de {_fmt_br(data_inicio)} a {_fmt_br(data_fim)}'
        + (f'; CDI {ultima_taxa}% a.d.' if ultima_taxa is not None else '.')
    )
    return fator.quantize(Decimal('0.00000001')), total_dias, msg


def _contar_dias_uteis(
    data_inicio: date,
    data_fim: date,
    incluir_inicio: bool = False,
) -> int:
    """Conta dias de segunda a sexta no intervalo."""
    if data_fim < data_inicio:
        return 0
    n = 0
    d = data_inicio if incluir_inicio else data_inicio + timedelta(days=1)
    while d <= data_fim:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def juros_cdi_sobre_saldo(
    saldo: Decimal,
    data_inicio: date,
    data_fim: date,
    pct_indice: Decimal = Decimal('100'),
    taxa_manual_periodo_pct: Optional[Decimal] = None,
    series: list[tuple[date, Decimal]] | None = None,
    incluir_data_inicio: bool = False,
    taxa_prefixada_am: Optional[Decimal] = None,
) -> tuple[Decimal, dict]:
    """
    Juros CDI (e opcionalmente taxa prefixada a.m.) sobre saldo no período.
    Manual: saldo × (taxa_periodo%/100) × (pct_indice/100) [sem fator prefixado].
    Com taxa_prefixada_am (SACD): J = saldo × (fator_CDI × fator_taxa − 1).
    """
    saldo = saldo or Decimal('0')
    pct = pct_indice if pct_indice is not None else Decimal('100')
    detalhe: dict = {
        'fonte': '',
        'fator': Decimal('1'),
        'fator_cdi': Decimal('1'),
        'fator_taxa': Decimal('1'),
        'dias_uteis': 0,
        'dias_corridos': 0,
        'mensagem': '',
        'pct_indice': pct,
        'taxa_prefixada_am': taxa_prefixada_am or Decimal('0'),
    }

    if saldo <= 0 or data_fim < data_inicio:
        detalhe['mensagem'] = 'Sem saldo ou período inválido.'
        return Decimal('0.00'), detalhe
    if data_fim == data_inicio and not incluir_data_inicio:
        detalhe['mensagem'] = 'Sem saldo ou período inválido.'
        return Decimal('0.00'), detalhe

    if taxa_manual_periodo_pct is not None and str(taxa_manual_periodo_pct).strip() != '':
        taxa = Decimal(str(taxa_manual_periodo_pct))
        fator = Decimal('1') + (taxa / Decimal('100')) * (pct / Decimal('100'))
        fator_taxa, dias_c = fator_taxa_prefixada_am(taxa_prefixada_am, data_inicio, data_fim)
        fator_total = fator * fator_taxa
        juros = (saldo * (fator_total - Decimal('1'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        detalhe.update({
            'fonte': 'manual',
            'fator': fator_total,
            'fator_cdi': fator,
            'fator_taxa': fator_taxa,
            'dias_corridos': dias_c,
            'mensagem': (
                f'Taxa CDI manual do período: {taxa}% '
                f'(aplicado {pct}% do índice)'
                + (
                    f' × taxa {taxa_prefixada_am}% a.m. ({dias_c} d)'
                    if fator_taxa != 1 else ''
                )
                + '.'
            ),
        })
        return juros, detalhe

    fator, dias, msg = fator_cdi_periodo(
        data_inicio,
        data_fim,
        pct_indice=pct,
        series=series,
        incluir_data_inicio=incluir_data_inicio,
    )
    fator_taxa, dias_c = fator_taxa_prefixada_am(taxa_prefixada_am, data_inicio, data_fim)
    fator_total = fator * fator_taxa
    juros = (saldo * (fator_total - Decimal('1'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if fator_taxa != 1:
        msg = (
            f'{msg} × taxa prefixada {taxa_prefixada_am}% a.m. '
            f'({dias_c} dia(s) corridos / 30).'
        )
    detalhe.update({
        'fonte': 'bcb',
        'fator': fator_total,
        'fator_cdi': fator,
        'fator_taxa': fator_taxa,
        'dias_uteis': dias,
        'dias_corridos': dias_c,
        'mensagem': msg,
    })
    return juros, detalhe
