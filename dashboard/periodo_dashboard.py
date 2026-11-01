"""Período do dashboard: mês ou intervalo personalizado (máx. 368 dias)."""
from __future__ import annotations

from calendar import monthrange
from datetime import date

MAX_INTERVALO_DASHBOARD_DIAS = 368


def parse_data_iso(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        partes = str(valor).strip().split('-')
        if len(partes) != 3:
            return None
        return date(int(partes[0]), int(partes[1]), int(partes[2]))
    except (TypeError, ValueError):
        return None


def validar_intervalo_dashboard(data_inicio: date, data_fim: date) -> str | None:
    if data_fim < data_inicio:
        return 'A data final deve ser igual ou posterior à data inicial.'
    dias = (data_fim - data_inicio).days
    if dias > MAX_INTERVALO_DASHBOARD_DIAS:
        return (
            f'O intervalo não pode passar de {MAX_INTERVALO_DASHBOARD_DIAS} dias '
            f'(selecionado: {dias + 1} dias).'
        )
    return None


def rotulo_cabecalho_relatorio(ano: int, mes: int, inicio: date, fim: date) -> str:
    from faturamento_medico.dashboard_exames import MESES_PT

    ultimo = monthrange(ano, mes)[1]
    if inicio == date(ano, mes, 1) and fim == date(ano, mes, ultimo):
        return f'{MESES_PT[mes].upper()} {ano}'
    return f'{inicio.strftime("%d/%m/%Y")} — {fim.strftime("%d/%m/%Y")}'


def resolver_inicio_fim(
    ano: int,
    mes: int,
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> tuple[date, date]:
    if data_inicio and data_fim:
        return data_inicio, data_fim
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    return inicio, fim


def titulo_periodo(inicio: date, fim: date, *, mensal: bool) -> str:
    from faturamento_medico.dashboard_exames import MESES_PT

    if mensal and inicio.day == 1 and fim.day == monthrange(fim.year, fim.month)[1]:
        if inicio.year == fim.year and inicio.month == fim.month:
            return f'{MESES_PT[inicio.month - 1]} de {inicio.year}'
    return f'{inicio.strftime("%d/%m/%Y")} — {fim.strftime("%d/%m/%Y")}'
