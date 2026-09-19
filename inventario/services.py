from django.contrib.auth.models import User

from estoque.models import ProdutoEstoque
from inventario.models import Inventario, InventarioItem, InventarioResponsavelContagem


def popular_itens_do_estoque(inventario: Inventario) -> int:
    produtos = ProdutoEstoque.objects.filter(empresa_id=inventario.empresa_id).order_by(
        'codigo_produto',
    )
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
            quantidade_estoque=p.quantidade_estoque,
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
    if usuario.is_superuser:
        return True
    return InventarioResponsavelContagem.objects.filter(
        inventario=inventario,
        rodada=rodada,
        usuario=usuario,
    ).exists()
