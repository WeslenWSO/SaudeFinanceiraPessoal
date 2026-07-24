from django import views
from django.conf.urls.static import static
from django.urls import path
from .views import *
from regrarateio import views

from SaudeFinanceira import settings


app_name = 'regrarateio'

urlpatterns = [

    path("regraList/", RegraList.as_view(), name='regraList'),
    path("regraIList/<int:pk>/", RegraIList.as_view(), name='regraIList'),
    path('regra/create/', RegraCreate.as_view(), name='regra-create'),
    path("regraI/create/", RegraICreate.as_view(), name='regraI-create'),
    path("regraI/update/<int:pk>", RegraIUpdate.as_view(), name='regraI-update'),
    path("regraI/delete/<int:pk>", views.RegraIDelete, name='regraI-delete'),
    path("regra/update/<int:pk>", RegraUpdate.as_view(), name="regra-update"),
    path("regra/delete/<int:pk>", views.RegraDelete, name="regra-delete"),
    path("lancamentos/", views.LancamentoRateioList.as_view(), name="lancamentoRateioList"),
    path(
        "lancamentos/editar/<str:origem>/<int:titulo_id>/",
        views.LancamentoRateioGrupoEdit.as_view(),
        name="lancamentoRateioEdit",
    ),
    path(
        "lancamentos/excluir/<int:pk>/",
        views.lancamento_rateio_delete,
        name="lancamentoRateioDelete",
    ),
    path(
        "lancamentos/contas-pagar-candidatas/",
        views.contas_pagar_rateio_candidatas,
        name="contasPagarRateioCandidatas",
    ),
    path(
        "lancamentos/contas-receber-candidatas/",
        views.contas_receber_rateio_candidatas,
        name="contasReceberRateioCandidatas",
    ),
    path("lancamentos/gerar/cap/", views.gerar_rateio_contas_pagar_aplicar, name="gerarRateioCap"),
    path("lancamentos/gerar/car/", views.gerar_rateio_contas_receber_aplicar, name="gerarRateioCar"),
        ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)