from django.conf.urls.static import static
from django.urls import path

from . import views

from .views import *
from . import views

from SaudeFinanceira import settings


app_name = 'contasapagar'

urlpatterns = [
    path('', views.listar_contas_a_pagar, name='listaAPagar'),
    path('cadastrar/', views.cadastrar_conta_a_pagar, name='cadastrar'),
    path('editar/<int:pk>/', views.editar_conta_a_pagar, name='editar'),
    path('baixar/<int:pk>/', views.baixar_conta_a_pagar, name='baixar'),
    path('excluir/<int:pk>/', views.excluir_conta_a_pagar, name='excluir'),
    path('desconciliar/', views.desconciliar_contas_pagar, name='desconciliar'),
    path('detalhes/<str:tipo>/<int:id>/', views.detalhes_modal, name='detalhes_modal'),
    path('buscar_lancamentos_conciliacao/<int:conta_banco_id>/', views.buscar_lancamentos_conciliacao, name='buscar_lancamentos_conciliacao'),
    path('importar_pdf/', views.importar_pdf_contas_pagar, name='importar_pdf'),
    path(
        'importar_relatorio_liquidos/',
        views.importar_relatorio_liquidos,
        name='importar_relatorio_liquidos',
    ),
    path('baixar_selecionadas/', views.baixar_contas_selecionadas, name='baixar_selecionadas'),
    path('categorizar-baixados/', views.categorizar_pagos_baixados, name='categorizar_baixados'),
    path('buscar_categorias/', views.buscar_categorias, name='buscar_categorias'),
    path('aplicar_categoria/', views.aplicar_categoria, name='aplicar_categoria'),
    #path('Pagas/', views.contasapagas, name='listaAPagar'),

    ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)