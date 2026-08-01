from django.urls import path

from . import views

app_name = 'planejamento_orcamentario'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('real-plan/', views.visao_real_plan, name='visao_real_plan'),
    path('exportar-excel/', views.exportar_excel, name='exportar_excel'),
    path('item/<int:pk>/editar/', views.editar, name='editar'),
    path('item/<int:pk>/excluir/', views.excluir, name='excluir'),
    path('<str:tipo>/', views.listar_tipo, name='listar_tipo'),
    path('<str:tipo>/novo/', views.criar, name='criar'),
]
