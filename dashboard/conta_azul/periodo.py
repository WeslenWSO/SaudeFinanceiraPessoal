"""Período de integração Conta Azul (dia único ou intervalo ≤ 31 dias)."""

from __future__ import annotations

from datetime import date

MAX_DIAS_INTERVALO_CA = 31


def parse_periodo_integracao_ca(post) -> tuple[date | None, date | None, str | None]:
    """Retorna (data_de, data_ate, mensagem_erro). Intervalo inclusive ≤ 31 dias."""
    from django.utils.dateparse import parse_date as django_parse_date

    modo = (post.get('ca_periodo_modo') or 'intervalo').strip().lower()
    if modo == 'dia':
        dia = django_parse_date((post.get('ca_periodo_dia') or '').strip())
        if not dia:
            return None, None, 'Informe o dia para buscar no Conta Azul.'
        return dia, dia, None

    d_ini = django_parse_date((post.get('ca_data_de') or '').strip())
    d_fim = django_parse_date((post.get('ca_data_ate') or '').strip())
    if not d_ini or not d_fim:
        return None, None, 'Informe data inicial e final (máx. 31 dias).'
    if d_ini > d_fim:
        return None, None, 'A data inicial não pode ser maior que a final.'
    dias = (d_fim - d_ini).days + 1
    if dias > MAX_DIAS_INTERVALO_CA:
        return (
            None,
            None,
            f'O intervalo tem {dias} dias; use no máximo {MAX_DIAS_INTERVALO_CA} dias por execução.',
        )
    return d_ini, d_fim, None
