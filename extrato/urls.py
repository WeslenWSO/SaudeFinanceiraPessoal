from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    LancamentoListView, LancamentoCreateView, LancamentoUpdateView, LancamentoDeleteView,
    UploadOFXView, UploadPDFView, ExtratoPreviaView, ConfirmarImportacaoView,
    ContaBancariaListView, ContaBancariaCreateView, ContaBancariaUpdateView, ContaBancariaDeleteView,
    ConciliarView, DesconciliarView, ExtratoMovimentoListView,
    transferir_view, detalhes_modal, lancamento_relatorios_view, exportar_conciliacao_view,
    conciliar_despesa_view, conciliar_multiplo_view, buscar_contas_conciliacao_multipla,
    conciliar_automatico_view,
    importar_extrato_sicoob,
)

app_name = "extrato"

urlpatterns = [
    path("contas-bancarias/", ContaBancariaListView.as_view(), name="conta_bancaria_list"),
    path("contas-bancarias/novo/", ContaBancariaCreateView.as_view(), name="conta_bancaria_new"),
    path("contas-bancarias/<int:pk>/editar/", ContaBancariaUpdateView.as_view(), name="conta_bancaria_edit"),
    path("contas-bancarias/<int:pk>/excluir/", ContaBancariaDeleteView.as_view(), name="conta_bancaria_delete"),

    path("lancamentos/", LancamentoListView.as_view(), name="lancamento_list"),
    path("lancamentos/novo/", LancamentoCreateView.as_view(), name="lancamento_new"),
    path("lancamentos/<int:pk>/editar/", LancamentoUpdateView.as_view(), name="lancamento_edit"),
    path("lancamentos/<int:pk>/excluir/", LancamentoDeleteView.as_view(), name="lancamento_delete"),

    path("extrato/sicoob/importar/", importar_extrato_sicoob, name="importar_sicoob"),
    path("extrato/ofx/", UploadOFXView.as_view(), name="upload_ofx"),
    path("extrato/pdf/", UploadPDFView.as_view(), name="upload_pdf"),
    path("extrato/previsao/<int:extrato_arquivo_id>/", ExtratoPreviaView.as_view(), name="extrato_previa"),
    path("extrato/confirmar-importacao/<int:extrato_arquivo_id>/", ConfirmarImportacaoView.as_view(), name="confirmar_importacao"),

    path("conciliar/", ConciliarView.as_view(), name="conciliar"),
    path("desconciliar/", DesconciliarView.as_view(), name="desconciliar"),

    path("movimentos/", ExtratoMovimentoListView.as_view(), name="extrato_movimento_list"),
    path("transferir/", transferir_view, name="transferir"),
    path("conciliar_despesa/", conciliar_despesa_view, name="conciliar_despesa"),
    path("conciliar_automatico/", conciliar_automatico_view, name="conciliar_automatico"),
    path("conciliar_multiplo/<int:lancamento_id>/", conciliar_multiplo_view, name="conciliar_multiplo"),
    path("buscar_contas_conciliacao_multipla/<int:lancamento_id>/", buscar_contas_conciliacao_multipla, name="buscar_contas_conciliacao_multipla"),
    path("detalhes/<str:tipo>/<int:id>/", detalhes_modal, name="detalhes_modal"),
    path("lancamentos/<int:lancamento_id>/relatorios/", lancamento_relatorios_view, name="lancamento_relatorios"),
    path("exportar_conciliacao/", exportar_conciliacao_view, name="exportar_conciliacao"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)