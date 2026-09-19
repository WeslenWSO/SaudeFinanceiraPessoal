from django.urls import path

from estoque.views import (
    ProdutoEstoqueCreateView,
    ProdutoEstoqueListView,
    ProdutoEstoqueUpdateView,
    excluir_produto_estoque,
)

app_name = 'estoque'

urlpatterns = [
    path('', ProdutoEstoqueListView.as_view(), name='produto_list'),
    path('novo/', ProdutoEstoqueCreateView.as_view(), name='produto_create'),
    path('<int:pk>/editar/', ProdutoEstoqueUpdateView.as_view(), name='produto_update'),
    path('<int:pk>/excluir/', excluir_produto_estoque, name='produto_delete'),
]
