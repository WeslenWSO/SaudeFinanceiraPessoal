from django.urls import path

from . import views

app_name = 'opcartao'

urlpatterns = [
    path('cartoes/', views.cartao_listar, name='cartao_listar'),
    path('cartoes/novo/', views.cartao_novo, name='cartao_novo'),
    path('cartoes/<int:pk>/editar/', views.cartao_editar, name='cartao_editar'),
    path('cartoes/<int:pk>/excluir/', views.cartao_excluir, name='cartao_excluir'),
    path('', views.fatura_listar, name='fatura_listar'),
    path('importar/', views.fatura_importar, name='fatura_importar'),
    path('<int:pk>/', views.fatura_detalhe, name='fatura_detalhe'),
    path('<int:pk>/excluir/', views.fatura_excluir, name='fatura_excluir'),
]
