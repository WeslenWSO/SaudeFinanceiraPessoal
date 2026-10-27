"""Período de sincronização Conta Azul (limite de dias)."""

from __future__ import annotations

from datetime import date, datetime

MAX_DIAS_SYNC_CONTA_AZUL = 31


def periodo_sync_padrao(hoje: date | None = None) -> tuple[date, date]:
    hoje = hoje or date.today()
    return hoje.replace(day=1), hoje


def _parse_data(raw: str | None, *, padrao: date) -> date:
    texto = (raw or '').strip()
    if not texto:
        return padrao
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(f'Data inválida: {texto!r}. Use o formato AAAA-MM-DD.') from exc


def parse_periodo_sync(
    data_de_raw: str | None,
    data_ate_raw: str | None,
    *,
    hoje: date | None = None,
) -> tuple[date, date]:
    """
    Interpreta intervalo inclusivo. Levanta ValueError se fim < início ou > 31 dias.
    """
    hoje = hoje or date.today()
    padrao_de, padrao_ate = periodo_sync_padrao(hoje)
    data_de = _parse_data(data_de_raw, padrao=padrao_de)
    data_ate = _parse_data(data_ate_raw, padrao=padrao_ate)

    if data_ate < data_de:
        raise ValueError('A data final não pode ser anterior à data inicial.')

    dias = (data_ate - data_de).days + 1
    if dias > MAX_DIAS_SYNC_CONTA_AZUL:
        raise ValueError(
            f'O período tem {dias} dias. O máximo permitido é {MAX_DIAS_SYNC_CONTA_AZUL} dias '
            f'(inclusive). Reduza o intervalo ou sincronize em partes.'
        )
    return data_de, data_ate
