from django.urls import path

from orcamento_compra import views

app_name = 'orcamento_compra'

urlpatterns = [
    path('', views.listar, name='listar'),
    path('criar/', views.criar, name='criar'),
    path('<int:pk>/', views.detalhe, name='detalhe'),
    path('<int:pk>/excluir/', views.excluir, name='excluir'),
    path('<int:pk>/cabecalho/', views.atualizar_cabecalho, name='atualizar_cabecalho'),
    path('<int:pk>/itens/adicionar/', views.adicionar_item, name='adicionar_item'),
    path(
        '<int:pk>/produtos-comercio/buscar/',
        views.buscar_produto_comercio_ajax,
        name='buscar_produto_comercio_ajax',
    ),
    path('<int:pk>/itens/<int:item_id>/excluir/', views.excluir_item, name='excluir_item'),
    path('<int:pk>/itens/<int:item_id>/salvar/', views.salvar_item_ajax, name='salvar_item_ajax'),
    path('<int:pk>/fornecedores/adicionar/', views.adicionar_fornecedor, name='adicionar_fornecedor'),
    path('<int:pk>/fornecedores/<int:coluna_id>/excluir/', views.excluir_fornecedor, name='excluir_fornecedor'),
    path(
        '<int:pk>/fornecedores/<int:coluna_id>/pdf/',
        views.upload_pdf_fornecedor,
        name='upload_pdf_fornecedor',
    ),
    path(
        '<int:pk>/fornecedores/<int:coluna_id>/vincular-pdf/',
        views.vincular_pdf,
        name='vincular_pdf',
    ),
    path(
        '<int:pk>/fornecedores/<int:coluna_id>/vincular-pdf/salvar/',
        views.salvar_vinculo_pdf,
        name='salvar_vinculo_pdf',
    ),
    path('<int:pk>/precos/salvar/', views.salvar_preco_ajax, name='salvar_preco_ajax'),
    path('<int:pk>/gerar-vencedores/', views.gerar_vencedores, name='gerar_vencedores'),
    path(
        '<int:pk>/vencedor/<int:resultado_id>/imprimir/',
        views.imprimir_vencedor,
        name='imprimir_vencedor',
    ),
]
