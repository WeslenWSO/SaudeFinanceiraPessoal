from django.urls import path
from .views import (
    NFSeListView, NFSeCreateView, NFSeUpdateView,
    NFSeDetailView, NFSeDeleteView, NFSeRecebimentoView,
    XMLImportView, NfseEventoCancelamentoImportView, NfsePortalNacionalImportView, NfsePortalExtensaoView, NfseAdnImportView, import_xml_ajax,
    portal_extensao_credenciais,
    portal_extensao_executar_selenium,
    portal_extensao_importar_pasta_mes,
    aplicar_discriminacao_bulk,     aplicar_regra_imposto_bulk, aplicar_socio_bulk, aplicar_cobranca_bulk,
    gerar_contas_receber_bulk, excluir_nfse_bulk, extrair_discriminacao_ajax, get_filtered_ids, export_excel, NFSeSegmentView,
    detalhes_modal, ai_segmentacao, dashboard_nfse, retencoes_nota_ajax,
    calcular_adicional_trimestral, fechar_periodo, reabrir_periodo, export_apuracao_excel, apuracao_simples,
    anexos_simples_list, anexos_simples_create, anexos_simples_update, anexos_simples_delete,
    restaurar_nota_fiscal_view, listar_logs_notas_fiscais_view, marcar_nfse_cancelada,
)
from notasfiscais.views import apuracao_impostos


app_name = 'notasfiscais'

urlpatterns = [
    path('', NFSeListView.as_view(), name='list'),
    path('dashboard/', dashboard_nfse, name='dashboard'),
    path('create/', NFSeCreateView.as_view(), name='create'),
    path('import/', XMLImportView.as_view(), name='import'),
    path(
        'importar-eventos-cancelamento/',
        NfseEventoCancelamentoImportView.as_view(),
        name='import_evento_cancelamento',
    ),
    path(
        'importar-portal-nacional/',
        NfsePortalNacionalImportView.as_view(),
        name='portal_nacional_import',
    ),
    path(
        'importar-adn/',
        NfseAdnImportView.as_view(),
        name='adn_import',
    ),
    path(
        "importar-portal-extensao/",
        NfsePortalExtensaoView.as_view(),
        name="portal_extensao_import",
    ),
    path(
        "importar-portal-extensao/credenciais-portal/",
        portal_extensao_credenciais,
        name="portal_extensao_credenciais",
    ),
    path(
        "importar-portal-extensao/executar-selenium/",
        portal_extensao_executar_selenium,
        name="portal_extensao_selenium",
    ),
    path(
        "importar-portal-extensao/importar-pasta-mes/",
        portal_extensao_importar_pasta_mes,
        name="portal_extensao_importar_pasta_mes",
    ),
    path('import-ajax/', import_xml_ajax, name='import_ajax'),
    # Cancelar/reativar (antes de detail para evitar ambiguidade de reverse)
    path('<int:pk>/cancelar/', marcar_nfse_cancelada, name='marcar_cancelada'),
    path('<int:pk>/', NFSeDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', NFSeUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', NFSeDeleteView.as_view(), name='delete'),
    path('<int:pk>/recebimento/', NFSeRecebimentoView.as_view(), name='recebimento'),
    path('<int:pk>/segmentar/', NFSeSegmentView.as_view(), name='segment'),
    path("nfse/aplicar-discriminacao/", aplicar_discriminacao_bulk, name="nfse_aplicar_discriminacao_bulk"),
    path("nfse/aplicar-regra-imposto/", aplicar_regra_imposto_bulk, name="nfse_aplicar_regra_imposto_bulk"),
    path("nfse/aplicar-socio/", aplicar_socio_bulk, name="nfse_aplicar_socio_bulk"),
    path("nfse/aplicar-cobranca/", aplicar_cobranca_bulk, name="nfse_aplicar_cobranca_bulk"),
    path("nfse/gerar-contas-receber/", gerar_contas_receber_bulk, name="nfse_gerar_contas_receber_bulk"),
    path("nfse/excluir-selecionadas/", excluir_nfse_bulk, name="nfse_excluir_bulk"),
    path('extrair-discriminacao-ajax/', extrair_discriminacao_ajax, name='extrair_discriminacao_ajax'),
    path('get-filtered-ids/', get_filtered_ids, name='get_filtered_ids'),
    path('export-excel/', export_excel, name='export_excel'),
    path('export-apuracao-excel/', export_apuracao_excel, name='export_apuracao_excel'),
    path('ai-segmentacao/', ai_segmentacao, name='ai_segmentacao'),
    path('apuracao-impostos/', apuracao_impostos, name='apuracao_impostos'),
    path('apuracao-simples/', apuracao_simples, name='apuracao_simples'),
    path('anexos-simples/', anexos_simples_list, name='anexos_simples_list'),
    path('anexos-simples/create/', anexos_simples_create, name='anexos_simples_create'),
    path('anexos-simples/<int:pk>/update/', anexos_simples_update, name='anexos_simples_update'),
    path('anexos-simples/<int:pk>/delete/', anexos_simples_delete, name='anexos_simples_delete'),
    path('retencoes/<int:nota_id>/', retencoes_nota_ajax, name='retencoes_nota_ajax'),
    path('detalhes/<str:tipo>/<int:id>/', detalhes_modal, name='detalhes_modal'),
    path('calcular-adicional/', calcular_adicional_trimestral, name='calcular_adicional_trimestral'),
    path('detalhes-calculo/', calcular_adicional_trimestral, name='detalhes_calculo'),
    path('fechar-periodo/', fechar_periodo, name='fechar_periodo'),
    path('reabrir-periodo/', reabrir_periodo, name='reabrir_periodo'),
    path('logs-notas/', listar_logs_notas_fiscais_view, name='logs_notas_fiscais'),
    path('restaurar-nota/<int:log_id>/', restaurar_nota_fiscal_view, name='restaurar_nota_fiscal'),
]
