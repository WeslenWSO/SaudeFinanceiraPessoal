from django.urls import path

from inventario.views import (
    InventarioCreateView,
    InventarioDetailView,
    InventarioListView,
    InventarioUpdateView,
    inventario_aplicar_estoque,
    inventario_backup_estoque,
    inventario_backup_excel,
    inventario_contagem,
    inventario_definir_rodada_estoque,
    inventario_fechar,
    inventario_produtos,
    inventario_remover_item,
    inventario_sincronizar_estoque,
)

app_name = 'inventario'

urlpatterns = [
    path('', InventarioListView.as_view(), name='inventario_list'),
    path('novo/', InventarioCreateView.as_view(), name='inventario_create'),
    path('<int:pk>/', InventarioDetailView.as_view(), name='inventario_detail'),
    path('<int:pk>/config/', InventarioUpdateView.as_view(), name='inventario_config'),
    path('<int:pk>/contagem/<int:rodada>/', inventario_contagem, name='inventario_contagem'),
    path('<int:pk>/produtos/', inventario_produtos, name='inventario_produtos'),
    path(
        '<int:pk>/produtos/<int:item_id>/remover/',
        inventario_remover_item,
        name='inventario_remover_item',
    ),
    path('<int:pk>/sincronizar-estoque/', inventario_sincronizar_estoque, name='inventario_sincronizar'),
    path('<int:pk>/backup-estoque/', inventario_backup_estoque, name='inventario_backup'),
    path(
        '<int:pk>/backup/<int:backup_id>/excel/',
        inventario_backup_excel,
        name='inventario_backup_excel',
    ),
    path(
        '<int:pk>/rodada-estoque/',
        inventario_definir_rodada_estoque,
        name='inventario_rodada_estoque',
    ),
    path('<int:pk>/aplicar-estoque/', inventario_aplicar_estoque, name='inventario_aplicar_estoque'),
    path('<int:pk>/fechar/', inventario_fechar, name='inventario_fechar'),
]
