"""Cálculos SAC — taxa fixa a.m. com carência (parcela 0)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .taxas_parcela import multa_atraso_parcela, taxa_juros_am_parcela

# Carência na parcela 0; parcelas 1+ calculam juros SAC normalmente.

def juros_pro_rata_mensal(
    saldo: Decimal,
    taxa_juros_am: Decimal,
    data_inicio: date | None,
    data_fim: date | None,
) -> Decimal:
    """J = saldo × ((1 + i)^(dias/30) − 1)."""
    if saldo <= 0 or taxa_juros_am <= 0 or not data_inicio or not data_fim:
        return Decimal('0.00')
    dias = max(0, (data_fim - data_inicio).days)
    if dias <= 0:
        dias = 30
    i = taxa_juros_am / Decimal('100')
    fator = (Decimal('1') + i) ** (Decimal(dias) / Decimal('30'))
    return (saldo * (fator - Decimal('1'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _numero_parcela(parcela: Any) -> int:
    if hasattr(parcela, 'numero'):
        return int(parcela.numero or 0)
    return int(parcela.get('numero') or 0)


def _vencimento_parcela(parcela: Any) -> date | None:
    if hasattr(parcela, 'data_vencimento'):
        return parcela.data_vencimento
    return parcela.get('data_vencimento')


def _get_decimal(parcela: Any, campo: str) -> Decimal:
    if isinstance(parcela, dict):
        return parcela.get(campo) or Decimal('0')
    return getattr(parcela, campo, None) or Decimal('0')


def _get_historico(parcela: Any) -> str:
    if isinstance(parcela, dict):
        return str(parcela.get('historico') or '').strip()
    return str(parcela.historico or '').strip()


def _set_campo(parcela: Any, campo: str, valor: Any) -> None:
    if isinstance(parcela, dict):
        parcela[campo] = valor
    else:
        setattr(parcela, campo, valor)


def _amort_fixa_sac(
    valor_contrato: Decimal,
    parcelas: list[Any],
    pagas: list[Any],
) -> Decimal:
    for p in reversed(pagas):
        amort = _get_decimal(p, 'amortizacao')
        if amort > 0:
            return amort.quantize(Decimal('0.01'))
    for p in parcelas:
        if _numero_parcela(p) == 0:
            continue
        amort = _get_decimal(p, 'amortizacao')
        if amort > 0:
            return amort.quantize(Decimal('0.01'))
    n_amort = sum(1 for p in parcelas if _numero_parcela(p) != 0)
    if n_amort <= 0:
        n_amort = len(parcelas) or 1
    return (valor_contrato / Decimal(n_amort)).quantize(Decimal('0.01'))


def _tem_parcela_carencia(abertas: list[Any]) -> bool:
    return any(_numero_parcela(p) == 0 for p in abertas)


def _meses_carencia(data_inicio: date, vencimento_p0: date) -> int:
    """Meses de carência entre operação e vencimento da parcela 0."""
    dias = max(1, (vencimento_p0 - data_inicio).days)
    return max(1, round(dias / 30))


def _juros_carencia_divididos(
    *,
    saldo_inicial: Decimal,
    taxa_juros_am: Decimal,
    data_inicio: date | None,
    vencimento_p0: date | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Juros da carência: 1/mês na parcela 0 (linha); restante incorporado ao saldo.
    Retorna (juros_linha_p0, juros_capitalizados, saldo_pos_carencia).
    """
    if (
        saldo_inicial <= 0
        or taxa_juros_am <= 0
        or not data_inicio
        or not vencimento_p0
    ):
        return Decimal('0.00'), Decimal('0.00'), saldo_inicial

    juros_total = juros_pro_rata_mensal(
        saldo_inicial,
        taxa_juros_am,
        data_inicio,
        vencimento_p0,
    )
    meses = _meses_carencia(data_inicio, vencimento_p0)
    juros_linha_p0 = (juros_total / Decimal(meses)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    juros_capitalizados = (juros_total - juros_linha_p0).quantize(Decimal('0.01'))
    saldo = (saldo_inicial + juros_capitalizados).quantize(Decimal('0.01'))
    return juros_linha_p0, juros_capitalizados, saldo


def carencia_parcial_quitacao(
    *,
    principal: Decimal,
    taxa_juros_am: Decimal,
    data_operacao: date,
    data_quitacao: date,
    vencimento_p0: date,
) -> tuple[Decimal, Decimal]:
    """
    Carência parcial na quitação.
    Retorna (principal_base, juros_dias_restantes).
    principal_base = contrato + juros dos meses completos de carência capitalizados.
    juros_dias = pro-rata dos dias restantes sobre principal_base.
    Ex.: 1 mês + 3 dias → (350k + 1 mês juros, juros de 3 dias s/ base).
    """
    if principal <= 0 or taxa_juros_am <= 0 or data_quitacao <= data_operacao:
        return principal, Decimal('0.00')

    if data_quitacao >= vencimento_p0:
        juros_total = juros_pro_rata_mensal(
            principal, taxa_juros_am, data_operacao, vencimento_p0,
        )
        return (principal + juros_total).quantize(Decimal('0.01')), Decimal('0.00')

    juros_total = juros_pro_rata_mensal(
        principal, taxa_juros_am, data_operacao, vencimento_p0,
    )
    meses = _meses_carencia(data_operacao, vencimento_p0)
    juros_mes = (juros_total / Decimal(meses)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    dias = (data_quitacao - data_operacao).days
    meses_completos = dias // 30
    juros_meses = (juros_mes * Decimal(meses_completos)).quantize(Decimal('0.01'))
    principal_base = (principal + juros_meses).quantize(Decimal('0.01'))
    data_base = data_operacao + timedelta(days=meses_completos * 30)
    juros_dias = Decimal('0.00')
    if data_quitacao > data_base:
        juros_dias = juros_pro_rata_mensal(
            principal_base, taxa_juros_am, data_base, data_quitacao,
        )
    return principal_base, juros_dias


def juros_carencia_parcial_quitacao(
    *,
    principal: Decimal,
    taxa_juros_am: Decimal,
    data_operacao: date,
    data_quitacao: date,
    vencimento_p0: date,
) -> Decimal:
    """Soma juros da carência parcial (meses + dias). Preferir carencia_parcial_quitacao."""
    base, juros_dias = carencia_parcial_quitacao(
        principal=principal,
        taxa_juros_am=taxa_juros_am,
        data_operacao=data_operacao,
        data_quitacao=data_quitacao,
        vencimento_p0=vencimento_p0,
    )
    return (base + juros_dias - principal).quantize(Decimal('0.01'))


def saldo_quitacao_sac_taxa_fixa(
    *,
    valor_contrato: Decimal,
    taxa_juros_am: Decimal,
    data_operacao: date | None,
    data_quitacao: date,
    vencimento_p0: date | None,
    pago_amort: Decimal = Decimal('0'),
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Saldo p/ quitação SAC taxa fixa com carência.
    Retorna (principal_base, juros, total).
    """
    principal = (valor_contrato - pago_amort).quantize(Decimal('0.01'))
    if principal < 0:
        principal = Decimal('0.00')
    if not data_operacao or not vencimento_p0 or taxa_juros_am <= 0:
        return principal, Decimal('0.00'), principal

    if data_quitacao < vencimento_p0:
        principal_base, juros = carencia_parcial_quitacao(
            principal=principal,
            taxa_juros_am=taxa_juros_am,
            data_operacao=data_operacao,
            data_quitacao=data_quitacao,
            vencimento_p0=vencimento_p0,
        )
        total = (principal_base + juros).quantize(Decimal('0.01'))
        return principal_base, juros, total

    _juros_p0, _juros_cap, saldo = _juros_carencia_divididos(
        saldo_inicial=principal,
        taxa_juros_am=taxa_juros_am,
        data_inicio=data_operacao,
        vencimento_p0=vencimento_p0,
    )
    juros = Decimal('0.00')
    if data_quitacao > vencimento_p0:
        juros = juros_pro_rata_mensal(saldo, taxa_juros_am, vencimento_p0, data_quitacao)
    total = (saldo + juros).quantize(Decimal('0.01'))
    return saldo, juros, total


def _processar_sac_taxa_fixa(
    *,
    abertas: list[Any],
    pagas: list[Any],
    parcelas_todas: list[Any],
    valor_contrato: Decimal,
    taxa_juros_am: Decimal,
    taxa_mora_am: Decimal,
    data_operacao: date | None,
    data_ref: date,
    persistir: bool,
) -> int:
    if not abertas or taxa_juros_am <= 0:
        return 0

    amort_fixa = _amort_fixa_sac(valor_contrato, parcelas_todas, pagas)
    n_parcelas_amort = sum(1 for p in parcelas_todas if _numero_parcela(p) > 0) or 1
    pago_amort = sum(_get_decimal(p, 'amortizacao') for p in pagas)
    saldo = (valor_contrato - pago_amort).quantize(Decimal('0.01'))
    if saldo < 0:
        saldo = Decimal('0.00')

    if pagas:
        ultima_paga = max(
            pagas,
            key=lambda p: (_vencimento_parcela(p) or date.min, _numero_parcela(p)),
        )
        data_ant = (
            _vencimento_parcela(ultima_paga)
            or getattr(ultima_paga, 'data_pagamento', None)
            or (ultima_paga.get('data_pagamento') if isinstance(ultima_paga, dict) else None)
            or data_operacao
        )
    else:
        data_ant = data_operacao
    if not data_ant:
        return 0

    abertas_ord = sorted(abertas, key=_numero_parcela)
    usa_juros_na_p0 = _tem_parcela_carencia(abertas_ord)
    juros_parcela0 = Decimal('0.00')
    parcela0 = next((p for p in abertas_ord if _numero_parcela(p) == 0), None)

    if usa_juros_na_p0 and parcela0:
        inicio_carencia = data_operacao or data_ant
        juros_parcela0, _juros_cap, saldo = _juros_carencia_divididos(
            saldo_inicial=saldo,
            taxa_juros_am=taxa_juros_am,
            data_inicio=inicio_carencia,
            vencimento_p0=_vencimento_parcela(parcela0),
        )
        # Amortização SAC sobre saldo pós-carência (principal + juros capitalizados) ÷ n parcelas
        amort_fixa = (saldo / Decimal(n_parcelas_amort)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )

    abertas_com_amort = [
        p for p in abertas_ord
        if _numero_parcela(p) != 0
    ]
    atualizadas = 0

    for idx, p in enumerate(abertas_ord):
        venc = _vencimento_parcela(p)
        if not venc:
            continue
        num = _numero_parcela(p)
        saldo_inicio = saldo.quantize(Decimal('0.01'))

        if num == 0 and usa_juros_na_p0:
            _set_campo(p, 'juros', juros_parcela0)
            _set_campo(p, 'amortizacao', Decimal('0.00'))
            _set_campo(p, 'valor_parcela', juros_parcela0)
            _set_campo(p, 'multa', Decimal('0.00'))
            hist = _get_historico(p)
            if 'carência' not in hist.lower() and 'carencia' not in hist.lower():
                msg = 'Carência (1/mês na parcela; restante no saldo)'
                _set_campo(
                    p,
                    'historico',
                    f'{hist} | {msg}'.strip(' |')[:200] if hist else msg,
                )
            data_ant = venc
        else:
            taxa_p = taxa_juros_am_parcela(
                p,
                taxa_juros_am=taxa_juros_am,
                taxa_mora_am=taxa_mora_am,
                data_ref=data_ref,
            )
            juros = juros_pro_rata_mensal(saldo_inicio, taxa_p, data_ant, venc)
            if usa_juros_na_p0:
                amort = amort_fixa
            else:
                amort = _get_decimal(p, 'amortizacao')
                if amort <= 0:
                    amort = amort_fixa
            idx_amort = abertas_com_amort.index(p) if p in abertas_com_amort else idx
            eh_ultima = idx_amort == len(abertas_com_amort) - 1
            if eh_ultima and saldo_inicio > 0:
                amort = saldo_inicio
            elif amort > saldo_inicio:
                amort = saldo_inicio
            amort = amort.quantize(Decimal('0.01'))
            _set_campo(p, 'juros', juros)
            _set_campo(p, 'amortizacao', amort)
            _set_campo(p, 'valor_parcela', (amort + juros).quantize(Decimal('0.01')))
            saldo = (saldo_inicio - amort).quantize(Decimal('0.01'))
            if saldo < 0:
                saldo = Decimal('0.00')
            data_ant = venc

        multa = multa_atraso_parcela(p, data_ref)
        _set_campo(p, 'multa', multa)

        if num != 0 or usa_juros_na_p0:
            hist = _get_historico(p)
            tag = 'Atualizada SAC (taxa fixa)'
            if tag not in hist:
                _set_campo(
                    p,
                    'historico',
                    f'{hist} | {tag}'.strip(' |')[:200] if hist else tag,
                )

        if persistir:
            p.save(update_fields=['amortizacao', 'juros', 'valor_parcela', 'multa', 'historico'])
        atualizadas += 1

    return atualizadas


def recalcular_sac_taxa_fixa_dicts(
    parcelas: list[dict[str, Any]],
    *,
    valor_contrato: Decimal,
    taxa_juros_am: Decimal,
    taxa_mora_am: Decimal = Decimal('0'),
    data_operacao: date | None,
    data_ref: date | None = None,
) -> list[dict[str, Any]]:
    """Recalcula juros/parcela em dicts (importação PDF)."""
    if not parcelas or taxa_juros_am <= 0:
        return parcelas

    pagas = [p for p in parcelas if p.get('status') == 'paga']
    abertas = [p for p in parcelas if p.get('status') != 'paga']
    if not abertas:
        return parcelas

    ref = data_ref or date.today()

    _processar_sac_taxa_fixa(
        abertas=abertas,
        pagas=pagas,
        parcelas_todas=parcelas,
        valor_contrato=valor_contrato,
        taxa_juros_am=taxa_juros_am,
        taxa_mora_am=taxa_mora_am,
        data_operacao=data_operacao,
        data_ref=ref,
        persistir=False,
    )
    return sorted(parcelas, key=lambda x: x.get('numero') or 0)


def recalcular_sac_taxa_fixa_modelos(
    *,
    parcelas: list[Any],
    abertas: list[Any],
    pagas: list[Any],
    valor_contrato: Decimal,
    taxa_juros_am: Decimal,
    taxa_mora_am: Decimal = Decimal('0'),
    data_operacao: date | None,
    data_ref: date | None = None,
) -> int:
    """Recalcula parcelas em aberto (modelos Django). Retorna qtd atualizada."""
    ref = data_ref or date.today()
    return _processar_sac_taxa_fixa(
        abertas=abertas,
        pagas=pagas,
        parcelas_todas=parcelas,
        valor_contrato=valor_contrato,
        taxa_juros_am=taxa_juros_am,
        taxa_mora_am=taxa_mora_am,
        data_operacao=data_operacao,
        data_ref=ref,
        persistir=True,
    )
