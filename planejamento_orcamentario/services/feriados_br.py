"""Feriados nacionais (Brasil) para calendário de planejamento."""

from __future__ import annotations

from datetime import date, timedelta


def _pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    pascoa = _pascoa(ano)
    fixos = {
        date(ano, 1, 1),
        date(ano, 4, 21),
        date(ano, 5, 1),
        date(ano, 9, 7),
        date(ano, 10, 12),
        date(ano, 11, 2),
        date(ano, 11, 15),
        date(ano, 12, 25),
    }
    moveis = {
        pascoa - timedelta(days=48),  # segunda de carnaval (aprox.)
        pascoa - timedelta(days=47),
        pascoa - timedelta(days=2),   # sexta-feira santa
        pascoa + timedelta(days=60),  # corpus christi
    }
    return fixos | moveis


def dia_util(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in feriados_nacionais(d.year)


def dia_nao_util(d: date) -> bool:
    return not dia_util(d)
