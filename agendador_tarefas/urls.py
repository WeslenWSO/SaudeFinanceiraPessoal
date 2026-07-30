from django.urls import path

from . import views

app_name = 'agendador_tarefas'

urlpatterns = [
    path('', views.tarefa_listar, name='listar'),
    path('nova/', views.tarefa_criar, name='criar'),
    path('<int:pk>/editar/', views.tarefa_editar, name='editar'),
    path('<int:pk>/excluir/', views.tarefa_excluir, name='excluir'),
    path('<int:pk>/status/', views.tarefa_alterar_status, name='alterar_status'),
]
