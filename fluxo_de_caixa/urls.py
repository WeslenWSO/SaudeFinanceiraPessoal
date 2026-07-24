from django.urls import path
from . import views

app_name = 'fluxo_de_caixa'

urlpatterns = [
    path('mensal/', views.fluxo_caixa_mensal, name='fluxo_caixa_mensal'),
    path('buscar_categorias/', views.buscar_categorias, name='buscar_categorias'),
]