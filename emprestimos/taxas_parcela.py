"""Taxas e encargos por situação da parcela (a vencer / atrasada)."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Multa por atraso: 2% sobre o valor da parcela (face).
MULTA_ATRASO_PCT = Decimal('2')


def _status_parcela(parcela: Any) -> str:
    if isinstance(parcela, dict):
        return str(parcela.get('status') or 'aberta')
    return str(getattr(parcela, 'status', None) or 'aberta')


def _vencimento_parcela(parcela: Any) -> date | None:
    if isinstance(parcela, dict):
        return parcela.get('data_vencimento')
    return getattr(parcela, 'data_vencimento', None)


def _valor_parcela_face(parcela: Any) -> Decimal:
    if isinstance(parcela, dict):
        v = parcela.get('valor_parcela') or Decimal('0')
    else:
        v = getattr(parcela, 'valor_parcela', None) or Decimal('0')
    if v > 0:
        return v.quantize(Decimal('0.01'))
    if isinstance(parcela, dict):
        return (
            (parcela.get('amortizacao') or Decimal('0'))
            + (parcela.get('juros') or Decimal('0'))
        ).quantize(Decimal('0.01'))
    return (
        (getattr(parcela, 'amortizacao', None) or Decimal('0'))
        + (getattr(parcela, 'juros', None) or Decimal('0'))
    ).quantize(Decimal('0.01'))


def situacao_parcela_aberta(parcela: Any, data_ref: date) -> str:
    """Retorna 'paga', 'atrasada' ou 'a_vencer'."""
    status = _status_parcela(parcela)
    if status != 'aberta':
        return 'paga'
    venc = _vencimento_parcela(parcela)
    if venc and venc < data_ref:
        return 'atrasada'
    return 'a_vencer'


def taxa_juros_am_efetiva(
    taxa_juros_am: Decimal,
    taxa_mora_am: Decimal,
    data_vencimento: date | None,
    data_ref: date,
    *,
    status: str = 'aberta',
) -> Decimal:
    """
    A vencer: só taxa de juros a.m.
    Atrasada: juros a.m. + mora a.m.
    """
    juros = taxa_juros_am or Decimal('0')
    if status != 'aberta':
        return juros.quantize(Decimal('0.0001'))
    if data_vencimento and data_vencimento < data_ref:
        juros = juros + (taxa_mora_am or Decimal('0'))
    return juros.quantize(Decimal('0.0001'))


def taxa_juros_am_parcela(
    parcela: Any,
    *,
    taxa_juros_am: Decimal,
    taxa_mora_am: Decimal,
    data_ref: date,
) -> Decimal:
    return taxa_juros_am_efetiva(
        taxa_juros_am,
        taxa_mora_am,
        _vencimento_parcela(parcela),
        data_ref,
        status=_status_parcela(parcela),
    )


def multa_atraso_valor(
    valor_parcela: Decimal,
    data_vencimento: date | None,
    data_ref: date,
    *,
    status: str = 'aberta',
    pct: Decimal = MULTA_ATRASO_PCT,
) -> Decimal:
    """Multa de 2% do valor da parcela quando em aberto e vencida."""
    if status != 'aberta' or not data_vencimento or data_vencimento >= data_ref:
        return Decimal('0.00')
    base = valor_parcela or Decimal('0')
    if base <= 0:
        return Decimal('0.00')
    return (base * pct / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def multa_atraso_parcela(
    parcela: Any,
    data_ref: date,
    *,
    pct: Decimal = MULTA_ATRASO_PCT,
) -> Decimal:
    return multa_atraso_valor(
        _valor_parcela_face(parcela),
        _vencimento_parcela(parcela),
        data_ref,
        status=_status_parcela(parcela),
        pct=pct,
    )
