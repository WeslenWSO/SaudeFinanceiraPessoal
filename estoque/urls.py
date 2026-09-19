from django.urls import path

from estoque.views import (
    ProdutoEstoqueCreateView,
    ProdutoEstoqueListView,
    ProdutoEstoqueUpdateView,
    excluir_produto_estoque,
    produto_importar_excel,
    produto_modelo_excel,
)

app_name = 'estoque'

urlpatterns = [
    path('', ProdutoEstoqueListView.as_view(), name='produto_list'),
    path('importar/', produto_importar_excel, name='produto_import'),
    path('modelo-excel/', produto_modelo_excel, name='produto_modelo_excel'),
    path('novo/', ProdutoEstoqueCreateView.as_view(), name='produto_create'),
    path('<int:pk>/editar/', ProdutoEstoqueUpdateView.as_view(), name='produto_update'),
    path('<int:pk>/excluir/', excluir_produto_estoque, name='produto_delete'),
]
