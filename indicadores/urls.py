from django.urls import path

from . import views
from . import views_dashboard
from . import views_lancamento

app_name = 'indicadores'

urlpatterns = [
    path('dashboard/', views_dashboard.dashboard_academia, name='dashboard_academia'),
    path('lancamento-vendas/', views_lancamento.LancamentoVendasList.as_view(), name='lancamento_vendas_listar'),
    path('lancamento-vendas/novo/', views_lancamento.LancamentoVendasCreate.as_view(), name='lancamento_vendas_criar'),
    path('lancamento-vendas/<int:pk>/editar/', views_lancamento.LancamentoVendasUpdate.as_view(), name='lancamento_vendas_editar'),
    path('lancamento-vendas/cancelamentos/novo/', views_lancamento.LancamentoCancelamentosCreate.as_view(), name='lancamento_cancelamentos_criar'),
    path('lancamento-vendas/<int:pk>/cancelamentos/', views_lancamento.LancamentoCancelamentosUpdate.as_view(), name='lancamento_cancelamentos_editar'),
    path('lancamento-vendas/<int:pk>/excluir/', views_lancamento.LancamentoVendasDelete.as_view(), name='lancamento_vendas_excluir'),
    path('atendentes/', views_lancamento.AtendenteList.as_view(), name='atendente_listar'),
    path('atendentes/novo/', views_lancamento.AtendenteCreate.as_view(), name='atendente_criar'),
    path('atendentes/<int:pk>/editar/', views_lancamento.AtendenteUpdate.as_view(), name='atendente_editar'),
    path('', views.IndicadorList.as_view(), name='listar'),
    path('novo/', views.IndicadorCreate.as_view(), name='criar'),
    path('<int:pk>/editar/', views.IndicadorUpdate.as_view(), name='editar'),
    path('<int:pk>/excluir/', views.IndicadorDelete.as_view(), name='excluir'),
]
