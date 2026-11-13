"""Valor exibido na coluna «Valor pago» (grade RIS e acerto de caixa)."""

from __future__ import annotations

from decimal import Decimal

from faturamento_medico.models import ItemServico

_EPS = Decimal('0.009')


def _valor_pago_parece_duplicado_ris(
    vp: Decimal,
    liquido: Decimal,
    item: ItemServico,
) -> bool:
    """
    RIS/MedCloud às vezes grava valor pago = 2× (ou N×) o total do item sem acréscimo real.
  """
    if liquido <= 0 or vp <= liquido + _EPS:
        return False
    acrescimo = _decimal_campo(getattr(item, 'valor_acrescimo', None)) or Decimal('0')
    if acrescimo > _EPS:
        return False
    try:
        razao = vp / liquido
    except Exception:
        return False
    qt = int(getattr(item, 'qt', None) or 1)
    if qt < 1:
        qt = 1
    candidatos = {2}
    if qt > 1:
        candidatos.add(qt)
    for n in candidatos:
        if abs(razao - Decimal(n)) <= Decimal('0.015'):
            return True
    return abs(vp - liquido * Decimal('2')) <= _EPS


def _decimal_campo(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _acrescimo_ris_eco_valor_pago(item: ItemServico) -> bool:
    """
    Planilha RIS às vezes repete o valor pago na coluna Acréscimo/Desconto (positivo).
    Somar de novo na grade dá o dobro (ex.: total 80 + acréscimo 80 → R$ 160).
    """
    base = item.total if item.total is not None else item.valor
    if base is None:
        return False
    base_dec = Decimal(str(base))
    if base_dec <= 0:
        return False
    vp = _decimal_campo(getattr(item, 'valor_pago', None))
    ac = _decimal_campo(getattr(item, 'valor_acrescimo', None)) or Decimal('0')
    if ac <= _EPS or vp is None or vp <= 0:
        return False
    return abs(ac - base_dec) <= _EPS and abs(vp - base_dec) <= _EPS


def _liquido_item(item: ItemServico) -> Decimal | None:
    base = item.total if item.total is not None else item.valor
    if base is None:
        return None
    bruto = Decimal(str(base))
    if bruto <= 0:
        return None
    acrescimo = _decimal_campo(getattr(item, 'valor_acrescimo', None)) or Decimal('0')
    desconto = _decimal_campo(getattr(item, 'valor_desconto', None)) or Decimal('0')
    if _acrescimo_ris_eco_valor_pago(item):
        acrescimo = Decimal('0')
    liquido = bruto + acrescimo - desconto
    return liquido if liquido > 0 else None


def valor_pago_para_exibicao(item: ItemServico | None) -> Decimal | None:
    """
    Preferência: valor_pago do RIS quando informado.
    Se zerado/ausente, usa total/valor conferido (ex.: após corrigir preço do convênio).
    Se valor_pago for maior que o total da tabela, usa valor_pago (ex.: acréscimo no caixa).
    Se valor_pago for menor que o total conferido, usa o total (RIS desatualizado).
    """
    if item is None:
        return None
    liquido = _liquido_item(item)
    vp_raw = getattr(item, 'valor_pago', None)
    vp = _decimal_campo(vp_raw)
    conferido = bool(getattr(item, 'conferido', False))

    if liquido is not None:
        if vp is None or vp <= 0:
            return liquido
        if vp > liquido + _EPS:
            if conferido or _valor_pago_parece_duplicado_ris(vp, liquido, item):
                return liquido
            return vp
        if vp + _EPS < liquido:
            return liquido
        return vp
    if vp is not None and vp > 0:
        return vp
    return None


def valor_agregacao_analises(item: ItemServico | None, faturamento) -> Decimal:
    """
    Relatórios (Análises / dashboard): mesma base do acerto de caixa — coluna Valor pago.
    Usa valor_pago_para_exibicao (tabela, acréscimo, desconto); aguardando faturamento
    com valor vazio usa total/valor do item.
    """
    try:
        from dashboard.analises_agendamento import eh_aguardando_faturamento_agendamento
    except ImportError:
        def eh_aguardando_faturamento_agendamento(_status):  # type: ignore[misc]
            return False

    aguardando = eh_aguardando_faturamento_agendamento(
        getattr(faturamento, 'status_agendamento', None)
    )

    if item is not None:
        vp = valor_pago_para_exibicao(item)
        if vp is not None and vp > 0:
            return vp
        if aguardando:
            bruto = item.total if item.total is not None else item.valor
            try:
                return Decimal(str(bruto or 0))
            except Exception:
                return Decimal('0')
        return vp if vp is not None else Decimal('0')

    vp_fat = _decimal_campo(getattr(faturamento, 'valor_pago', None))
    if vp_fat is not None and vp_fat != 0:
        return vp_fat
    if aguardando:
        tot = _decimal_campo(getattr(faturamento, 'total', None))
        if tot is not None and tot > 0:
            return tot
    val = _decimal_campo(getattr(faturamento, 'valor', None))
    acrescimo = _decimal_campo(getattr(faturamento, 'valor_acrescimo', None)) or Decimal('0')
    if val is not None:
        return val + acrescimo
    return Decimal('0')


def sincronizar_valor_pago_apos_preco(
    item: ItemServico,
    *,
    forcar: bool = False,
) -> None:
    """Após corrigir valor na tabela, alinha valor_pago ao total calculado."""
    total = item.total if item.total is not None else item.valor
    if total is None:
        return
    total_dec = Decimal(str(total))
    if total_dec <= 0:
        return
    vp_atual = _decimal_campo(item.valor_pago)
    if _acrescimo_ris_eco_valor_pago(item):
        ItemServico.objects.filter(pk=item.pk).update(valor_acrescimo=Decimal('0'))
        item.valor_acrescimo = Decimal('0')
    if vp_atual is not None and vp_atual > total_dec + _EPS:
        if _valor_pago_parece_duplicado_ris(vp_atual, total_dec, item):
            if item.valor_pago != total_dec:
                ItemServico.objects.filter(pk=item.pk).update(valor_pago=total_dec)
                item.valor_pago = total_dec
            return
        if not forcar:
            return
    if item.valor_pago != total_dec:
        ItemServico.objects.filter(pk=item.pk).update(valor_pago=total_dec)
        item.valor_pago = total_dec
