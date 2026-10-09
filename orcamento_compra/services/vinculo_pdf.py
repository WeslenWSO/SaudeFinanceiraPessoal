"""Grava de-para PDF → itens do orçamento e preços na coluna do fornecedor."""
from __future__ import annotations

from decimal import Decimal

from orcamento_compra.models import (
    OrcamentoCompraFornecedor,
    OrcamentoCompraItem,
    OrcamentoCompraPreco,
)
from orcamento_compra.services.pdf_linhas import aplicar_sugestoes, extrair_linhas_orcamento_pdf


def atualizar_linhas_do_texto(col: OrcamentoCompraFornecedor) -> list[dict]:
    linhas = extrair_linhas_orcamento_pdf(col.pdf_texto or '')
    itens = list(col.orcamento.itens.order_by('ordem', 'id'))
    # Preserva vínculos existentes por descrição similar
    antigas = {(_normalizar_desc(l.get('descricao')), l.get('item_id')) for l in (col.pdf_linhas or [])}
    linhas = aplicar_sugestoes(linhas, itens)
    for linha in linhas:
        chave = _normalizar_desc(linha.get('descricao'))
        for desc_ant, item_id in antigas:
            if item_id and desc_ant and chave == desc_ant:
                linha['item_id'] = item_id
                break
    return linhas


def _normalizar_desc(txt: str) -> str:
    return (txt or '').strip().lower()[:120]


def aplicar_vinculos_pdf(
    col: OrcamentoCompraFornecedor,
    linhas: list[dict],
) -> tuple[int, int]:
    """
    Salva pdf_linhas e preenche OrcamentoCompraPreco.
    Retorna (qtd_vinculos, qtd_precos_atualizados).
    """
    itens_map = {
        it.pk: it
        for it in OrcamentoCompraItem.objects.filter(orcamento_id=col.orcamento_id)
    }
    vinculos = 0
    precos_ok = 0
    col.pdf_linhas = linhas
    col.save(update_fields=['pdf_linhas'])

    for linha in linhas:
        item_id = linha.get('item_id')
        if not item_id:
            continue
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            continue
        item = itens_map.get(item_id)
        if not item:
            continue
        vinculos += 1

        total = _decimal(linha.get('preco_total'))
        unit = _decimal(linha.get('preco_unit'))
        if total is None and unit is not None:
            total = (unit * item.quantidade).quantize(Decimal('0.01'))
        if unit is None and total is not None and item.quantidade:
            unit = (total / item.quantidade).quantize(Decimal('0.0001'))

        if total is None and unit is None:
            continue

        preco, _ = OrcamentoCompraPreco.objects.get_or_create(
            item=item,
            coluna_fornecedor=col,
        )
        preco.preco_unitario = unit
        preco.preco_total = total
        preco.save(update_fields=['preco_unitario', 'preco_total'])
        precos_ok += 1

    return vinculos, precos_ok


def _decimal(val) -> Decimal | None:
    if val is None or val == '':
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None
