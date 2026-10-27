from django.contrib.auth.models import User

from estoque.models import NaturezaEstoque, ProdutoEstoque
from inventario.estoque_setor import quantidade_sistema_no_setor
from inventario.models import Inventario, InventarioItem, InventarioResponsavelContagem


def popular_itens_do_estoque(
    inventario: Inventario,
    *,
    produto_ids: list[int] | None = None,
) -> int:
    produtos = ProdutoEstoque.objects.filter(
        empresa_id=inventario.empresa_id,
        natureza=NaturezaEstoque.CONSUMIVEL,
    ).order_by('codigo_produto')
    setor = inventario.setor
    if produto_ids is not None:
        produtos = produtos.filter(pk__in=produto_ids)
    existentes = set(
        InventarioItem.objects.filter(inventario=inventario).values_list(
            'codigo_produto',
            flat=True,
        ),
    )
    novos = [
        InventarioItem(
            inventario=inventario,
            produto=p,
            codigo_produto=p.codigo_produto,
            descricao_produto=p.descricao,
            quantidade_estoque=quantidade_sistema_no_setor(p, setor),
            quantidade_estoque_contabil=p.quantidade_estoque_contabil,
        )
        for p in produtos
        if p.codigo_produto not in existentes
    ]
    if novos:
        InventarioItem.objects.bulk_create(novos)
    return len(novos)


def salvar_responsaveis(
    inventario: Inventario,
    por_rodada: dict[int, list[User]],
) -> None:
    InventarioResponsavelContagem.objects.filter(inventario=inventario).delete()
    bulk: list[InventarioResponsavelContagem] = []
    for rodada, usuarios in por_rodada.items():
        for usuario in usuarios:
            bulk.append(
                InventarioResponsavelContagem(
                    inventario=inventario,
                    rodada=rodada,
                    usuario=usuario,
                ),
            )
    if bulk:
        InventarioResponsavelContagem.objects.bulk_create(bulk)


def usuario_pode_contar(inventario: Inventario, usuario: User, rodada: int) -> bool:
    from inventario.permissoes import usuario_pode_acessar_inventario

    if not usuario_pode_acessar_inventario(usuario):
        return False
    responsaveis = InventarioResponsavelContagem.objects.filter(
        inventario=inventario,
        rodada=rodada,
    )
    if not responsaveis.exists():
        return True
    return responsaveis.filter(usuario=usuario).exists()
