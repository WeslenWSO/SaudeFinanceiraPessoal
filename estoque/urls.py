from django.urls import path

from estoque.views import (
    ProdutoEstoqueCreateView,
    ProdutoEstoqueListView,
    ProdutoEstoqueUpdateView,
    excluir_produto_estoque,
    produto_importar_excel,
    produto_modelo_excel,
)
from estoque.views_operacional import (
    EstoqueFarmaciaListView,
    ProdutoEstoqueOperacionalDetailView,
    RequisicaoListView,
    gerar_estoque_item_nota,
    relatorio_movimentos,
    requisicao_detail,
    requisicao_nova,
)

app_name = 'estoque'

urlpatterns = [
    path('farmacia/', EstoqueFarmaciaListView.as_view(), name='farmacia_list'),
    path('farmacia/produto/<int:pk>/', ProdutoEstoqueOperacionalDetailView.as_view(), name='produto_operacional_detail'),
    path('nf-item/<int:item_id>/gerar-estoque/', gerar_estoque_item_nota, name='gerar_estoque_nf_item'),
    path('requisicoes/', RequisicaoListView.as_view(), name='requisicao_list'),
    path('requisicoes/nova/', requisicao_nova, name='requisicao_nova'),
    path('requisicoes/<int:pk>/', requisicao_detail, name='requisicao_detail'),
    path('relatorios/movimentos/', relatorio_movimentos, name='relatorio_movimentos'),
    path('', ProdutoEstoqueListView.as_view(), name='produto_list'),
    path('importar/', produto_importar_excel, name='produto_import'),
    path('modelo-excel/', produto_modelo_excel, name='produto_modelo_excel'),
    path('novo/', ProdutoEstoqueCreateView.as_view(), name='produto_create'),
    path('<int:pk>/editar/', ProdutoEstoqueUpdateView.as_view(), name='produto_update'),
    path('<int:pk>/excluir/', excluir_produto_estoque, name='produto_delete'),
]
