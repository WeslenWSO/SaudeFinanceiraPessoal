"""De-para: código do produto na NF → produto no estoque."""

from __future__ import annotations

from estoque.models import ProdutoCodigoNotaDePara, ProdutoEstoque


def _norm_codigo(codigo: str) -> str:
    return (codigo or '').strip()


def buscar_produto_de_para(
    empresa_id: int,
    codigo_nota: str,
    fornecedor_id: int | None,
) -> ProdutoEstoque | None:
    codigo = _norm_codigo(codigo_nota)
    if not codigo:
        return None
    qs = ProdutoCodigoNotaDePara.objects.filter(
        empresa_id=empresa_id,
        codigo_nota=codigo,
    ).select_related('produto')
    if fornecedor_id:
        row = qs.filter(fornecedor_id=fornecedor_id).first()
        if row:
            return row.produto
    row = qs.filter(fornecedor__isnull=True).first()
    return row.produto if row else None


def gravar_de_para_nota(
    empresa,
    codigo_nota: str,
    fornecedor_id: int | None,
    produto: ProdutoEstoque,
    *,
    global_fornecedor: bool = False,
) -> None:
    codigo = _norm_codigo(codigo_nota)
    if not codigo or not produto.pk:
        return
    fid = None if global_fornecedor else fornecedor_id
    ProdutoCodigoNotaDePara.objects.update_or_create(
        empresa=empresa,
        codigo_nota=codigo,
        fornecedor_id=fid,
        defaults={'produto': produto},
    )


def situacao_codigo_nota(
    empresa_id: int,
    codigo_nota: str,
    fornecedor_id: int | None,
) -> dict:
    """
    Retorna flags para a UI de entrada NF.
    precisa_vinculo: código NF ≠ código no cadastro e ainda sem de-para.
    """
    codigo = _norm_codigo(codigo_nota)
    produto_mesmo_codigo = None
    if codigo:
        produto_mesmo_codigo = ProdutoEstoque.objects.filter(
            empresa_id=empresa_id,
            codigo_produto=codigo,
        ).first()
    produto_mapeado = buscar_produto_de_para(empresa_id, codigo, fornecedor_id)
    if produto_mesmo_codigo:
        return {
            'precisa_vinculo': False,
            'produto_destino': produto_mesmo_codigo,
            'codigo_sistema': produto_mesmo_codigo.codigo_produto,
            'via_de_para': False,
        }
    if produto_mapeado:
        return {
            'precisa_vinculo': False,
            'produto_destino': produto_mapeado,
            'codigo_sistema': produto_mapeado.codigo_produto,
            'via_de_para': True,
        }
    return {
        'precisa_vinculo': bool(codigo),
        'produto_destino': None,
        'codigo_sistema': '',
        'via_de_para': False,
    }
