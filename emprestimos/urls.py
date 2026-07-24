from django.urls import path

from . import views

app_name = 'emprestimos'

urlpatterns = [
    path('', views.emprestimo_list, name='listar'),
    path('parcelas-abertas/', views.emprestimo_parcelas_abertas, name='parcelas_abertas'),
    path('simulacoes/', views.emprestimo_simulacoes_list, name='simulacoes'),
    path('simulacoes/relatorio-sintetico/', views.emprestimo_simulacoes_relatorio_sintetico, name='simulacoes_relatorio_sintetico'),
    path('simulacoes/<int:pk>/excluir/', views.emprestimo_simulacao_excluir, name='simulacao_excluir'),
    path('importar/', views.emprestimo_importar, name='importar'),
    path('cadastrar/', views.emprestimo_cadastrar, name='cadastrar'),
    # Rotas específicas do contrato (antes de <pk>/)
    path('<int:pk>/importar-parcelas-pdf/', views.emprestimo_importar_parcelas_pdf, name='importar_parcelas_pdf'),
    path('<int:pk>/taxas/', views.emprestimo_atualizar_taxas, name='atualizar_taxas'),
    path('<int:pk>/quitar/', views.emprestimo_quitacao, name='quitacao'),
    path('<int:pk>/quitacao-juros-preview/', views.emprestimo_quitacao_juros_preview, name='quitacao_juros_preview'),
    path('<int:pk>/quitacao-excel/', views.emprestimo_quitacao_excel, name='quitacao_excel'),
    path('<int:pk>/sac-tabela-cdi/', views.emprestimo_sac_tabela_cdi, name='sac_tabela_cdi'),
    path('<int:pk>/atualizar-parcelas-sac/', views.emprestimo_atualizar_parcelas_sac, name='atualizar_parcelas_sac'),
    path('<int:pk>/atualizar-parcelas-price/', views.emprestimo_atualizar_parcelas_price, name='atualizar_parcelas_price'),
    path('<int:pk>/gerar-parcelas-sac/', views.emprestimo_gerar_parcelas_sac, name='gerar_parcelas_sac'),
    path('<int:pk>/excluir/', views.emprestimo_excluir, name='excluir'),
    path('<int:pk>/', views.emprestimo_detalhe, name='detalhe'),
]
