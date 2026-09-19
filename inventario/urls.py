from django.urls import path

from inventario.views import (
    InventarioCreateView,
    InventarioDetailView,
    InventarioListView,
    InventarioUpdateView,
    inventario_contagem,
    inventario_fechar,
    inventario_sincronizar_estoque,
)

app_name = 'inventario'

urlpatterns = [
    path('', InventarioListView.as_view(), name='inventario_list'),
    path('novo/', InventarioCreateView.as_view(), name='inventario_create'),
    path('<int:pk>/', InventarioDetailView.as_view(), name='inventario_detail'),
    path('<int:pk>/config/', InventarioUpdateView.as_view(), name='inventario_config'),
    path('<int:pk>/contagem/<int:rodada>/', inventario_contagem, name='inventario_contagem'),
    path('<int:pk>/sincronizar-estoque/', inventario_sincronizar_estoque, name='inventario_sincronizar'),
    path('<int:pk>/fechar/', inventario_fechar, name='inventario_fechar'),
]
