"""Valor exibido na coluna «Valor pago» (grade RIS e acerto de caixa)."""

from __future__ import annotations

from decimal import Decimal

from faturamento_medico.models import ItemServico


def _liquido_item(item: ItemServico) -> Decimal | None:
    base = item.total if item.total is not None else item.valor
    if base is None:
        return None
    bruto = Decimal(str(base))
    if bruto <= 0:
        return None
    desconto = Decimal(str(item.valor_desconto or 0))
    if desconto > 0:
        liquido = bruto - desconto
        return liquido if liquido > 0 else None
    return bruto


def valor_pago_para_exibicao(item: ItemServico | None) -> Decimal | None:
    """
    Preferência: valor_pago do RIS quando informado.
    Se zerado/ausente, usa total/valor conferido (ex.: após corrigir preço do convênio).
    Se valor_pago divergir do total conferido, usa o total (RIS desatualizado).
    """
    if item is None:
        return None
    liquido = _liquido_item(item)
    vp_raw = getattr(item, 'valor_pago', None)
    vp = Decimal(str(vp_raw)) if vp_raw is not None else None

    if liquido is not None:
        if vp is None or vp <= 0:
            return liquido
        if abs(vp - liquido) > Decimal('0.009'):
            return liquido
        return vp
    if vp is not None and vp > 0:
        return vp
    return None


def _decimal_campo(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def valor_agregacao_analises(item: ItemServico | None, faturamento) -> Decimal:
    """Relatórios de faturamento: valor_pago; se vazio ou zerado, campo valor do item."""
    alvo = item if item is not None else faturamento
    vp = _decimal_campo(getattr(alvo, 'valor_pago', None))
    if vp is not None and vp != 0:
        return vp
    val = _decimal_campo(getattr(alvo, 'valor', None))
    return val if val is not None else Decimal('0')


def sincronizar_valor_pago_apos_preco(item: ItemServico) -> None:
    """Após corrigir valor na tabela, alinha valor_pago ao total calculado."""
    total = item.total if item.total is not None else item.valor
    if total is None:
        return
    total_dec = Decimal(str(total))
    if total_dec <= 0:
        return
    if item.valor_pago != total_dec:
        item.valor_pago = total_dec
        item.save(update_fields=['valor_pago'])
