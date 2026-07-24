from django.urls import path
from . import views

app_name = 'contasareceber'

urlpatterns = [
    path('', views.listar_contas_a_receber, name='crlistar'),
    path('categorizar-baixados/', views.categorizar_recebidos_baixados, name='categorizar_baixados'),
    path('criar/', views.criar_conta_a_receber, name='criar'),
    path('autocomplete-cliente/', views.autocomplete_cliente, name='autocomplete_cliente'),
    path('buscar-lancamentos-extrato/', views.buscar_lancamentos_extrato, name='buscar_lancamentos_extrato'),
    path('buscar-lancamentos-selecionados/', views.buscar_lancamentos_selecionados, name='buscar_lancamentos_selecionados'),
    path('<int:pk>/editar/', views.editar_conta_a_receber, name='editar'),
    path('<int:pk>/baixar/', views.baixar_conta_a_receber, name='baixar'),
    path('<int:pk>/estornar/', views.estornar_conta_a_receber, name='estornar'),
    path('<int:pk>/deletar/', views.deletar_conta_a_receber, name='deletar'),
    path('<int:pk>/detalhes/', views.detalhes_conta_a_receber, name='detalhes'),
    path('baixar/', views.baixar_contas_a_receber, name='baixar_multiplas'),
    path('conciliar/', views.conciliar_contas_a_receber, name='conciliar'),
    path('lancar-selecionados/', views.lancar_contas_selecionadas, name='lancar_selecionados'),
    path('conciliar-cartao/', views.conciliar_cartao_por_autorizacao, name='conciliar_cartao'),
    path('sugerir-cartao-aprox/', views.sugerir_conciliacao_cartao_aproximacao, name='sugerir_cartao_aprox'),
    path('confirmar-cartao-aprox/', views.confirmar_conciliacao_cartao_aproximacao, name='confirmar_cartao_aprox'),
    path('baixas/', views.listar_baixas, name='listar_baixas'),
    path('nao-conciliados/', views.nao_conciliados, name='nao_conciliados'),
    path('nao-conciliados/excel/', views.nao_conciliados_excel, name='nao_conciliados_excel'),
    path('detalhes/<str:tipo>/<int:id>/', views.detalhes_modal, name='detalhes_modal'),
    path('baixar_dinheiro/', views.baixar_contas_dinheiro, name='baixar_dinheiro'),
    path('validar_contas_dinheiro/', views.validar_contas_dinheiro, name='validar_contas_dinheiro'),
    path('contas_caixa/', views.contas_caixa, name='contas_caixa'),
    path('buscar_categorias/', views.buscar_categorias, name='buscar_categorias'),
    path('aplicar_categoria/', views.aplicar_categoria, name='aplicar_categoria'),
    path('alterar-socio-lote/', views.alterar_socio_lote, name='alterar_socio_lote'),
    path('excluir-selecionados/', views.excluir_contas_selecionadas, name='excluir_selecionados'),
]