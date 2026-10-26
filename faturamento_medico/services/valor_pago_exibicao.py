"""Valor exibido na coluna «Valor pago» (grade RIS e acerto de caixa)."""

from __future__ import annotations

from decimal import Decimal

from faturamento_medico.models import ItemServico

_EPS = Decimal('0.009')


def _decimal_campo(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _liquido_item(item: ItemServico) -> Decimal | None:
    base = item.total if item.total is not None else item.valor
    if base is None:
        return None
    bruto = Decimal(str(base))
    if bruto <= 0:
        return None
    acrescimo = Decimal(str(getattr(item, 'valor_acrescimo', None) or 0))
    desconto = Decimal(str(item.valor_desconto or 0))
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
    vp = Decimal(str(vp_raw)) if vp_raw is not None else None

    if liquido is not None:
        if vp is None or vp <= 0:
            return liquido
        if vp > liquido + _EPS:
            return vp
        if vp + _EPS < liquido:
            return liquido
        return vp
    if vp is not None and vp > 0:
        return vp
    return None


def valor_agregacao_analises(item: ItemServico | None, faturamento) -> Decimal:
    """Relatórios de faturamento: valor_pago; se vazio ou zerado, campo valor do item."""
    alvo = item if item is not None else faturamento
    vp = _decimal_campo(getattr(alvo, 'valor_pago', None))
    if vp is not None and vp != 0:
        return vp
    val = _decimal_campo(getattr(alvo, 'valor', None))
    acrescimo = _decimal_campo(getattr(alvo, 'valor_acrescimo', None)) or Decimal('0')
    if val is not None:
        return val + acrescimo
    return Decimal('0')


def sincronizar_valor_pago_apos_preco(item: ItemServico) -> None:
    """Após corrigir valor na tabela, alinha valor_pago ao total calculado."""
    total = item.total if item.total is not None else item.valor
    if total is None:
        return
    total_dec = Decimal(str(total))
    if total_dec <= 0:
        return
    vp_atual = _decimal_campo(item.valor_pago)
    if vp_atual is not None and vp_atual > total_dec + _EPS:
        return
    if item.valor_pago != total_dec:
        item.valor_pago = total_dec
        item.save(update_fields=['valor_pago'])
