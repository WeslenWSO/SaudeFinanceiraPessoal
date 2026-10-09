"""Produtos distintos das NF de entrada tipo comércio (mesma base da tela Produtos comprados)."""
from __future__ import annotations

from django.db.models import Q

from notafiscalentrada.models import NotaFiscalEntradaItem


def listar_produtos_comercio_distintos(
    empresa_id: int,
    *,
    busca: str = '',
    limite: int = 800,
) -> list[dict]:
    """
    Um registro por código de produto, preferindo o nome/unidade da NF mais recente.
    """
    qs = (
        NotaFiscalEntradaItem.objects.filter(
            nota_fiscal__empresa_id=empresa_id,
            nota_fiscal__tipo_nota='comercio',
        )
        .select_related('nota_fiscal')
        .order_by('-nota_fiscal__data_emissao', '-nota_fiscal__id', '-numero_item')
    )
    busca = (busca or '').strip()
    if busca:
        qs = qs.filter(
            Q(nome_produto__icontains=busca) | Q(codigo_produto__icontains=busca),
        )

    por_codigo: dict[str, dict] = {}
    for item in qs.iterator(chunk_size=500):
        codigo = (item.codigo_produto or '').strip()
        if not codigo:
            continue
        if codigo in por_codigo:
            continue
        por_codigo[codigo] = {
            'codigo': codigo,
            'nome': (item.nome_produto or '').strip() or codigo,
            'unidade': (item.unidade or 'UN').strip() or 'UN',
            'ultimo_valor_unitario': item.valor_unitario,
            'ultima_emissao': item.nota_fiscal.data_emissao if item.nota_fiscal_id else None,
        }
        if len(por_codigo) >= limite:
            break

    return sorted(por_codigo.values(), key=lambda x: x['nome'].lower())


def serializar_produto_comercio(row: dict) -> dict:
    return {
        'codigo': row['codigo'],
        'nome': row['nome'],
        'unidade': row['unidade'],
        'ultimo_valor_unitario': str(row['ultimo_valor_unitario']),
    }


def dados_produto_comercio(empresa_id: int, codigo: str) -> dict | None:
    codigo = (codigo or '').strip()
    if not codigo:
        return None
    item = (
        NotaFiscalEntradaItem.objects.filter(
            nota_fiscal__empresa_id=empresa_id,
            nota_fiscal__tipo_nota='comercio',
            codigo_produto=codigo,
        )
        .select_related('nota_fiscal')
        .order_by('-nota_fiscal__data_emissao', '-nota_fiscal__id')
        .first()
    )
    if not item:
        return None
    return {
        'codigo': codigo,
        'nome': (item.nome_produto or '').strip() or codigo,
        'unidade': (item.unidade or 'UN').strip() or 'UN',
        'ultimo_valor_unitario': item.valor_unitario,
    }
