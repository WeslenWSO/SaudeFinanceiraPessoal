from django.conf.urls.static import static
from django.urls import path
from .views import *

from SaudeFinanceira import settings

app_name = 'servicos_medicos'

urlpatterns = [
    # Convenio
    path("convenio/", ConvenioList.as_view(), name='convenio_list'),
    path("convenio/create/", ConvenioCreate.as_view(), name='convenio_create'),
    path("convenio/<pk>/update/", ConvenioUpdate.as_view(), name='convenio_update'),

    # ServicosMedicos
    path("servicos/", ServicosMedicosList.as_view(), name='servicos_list'),
    path("servicos/create/", ServicosMedicosCreate.as_view(), name='servicos_create'),
    path("servicos/<pk>/update/", ServicosMedicosUpdate.as_view(), name='servicos_update'),

    # TabelaPreco
    path("tabela/", TabelaPrecoList.as_view(), name='tabela_list'),
    path("tabela/create/", TabelaPrecoCreate.as_view(), name='tabela_create'),
    path("tabela/<pk>/update/", TabelaPrecoUpdate.as_view(), name='tabela_update'),

    # Cabecalho
    path("cabecalho/", CabecalhoList.as_view(), name='cabecalho_list'),
    path("cabecalho/create/", CabecalhoCreate.as_view(), name='cabecalho_create'),
    path("cabecalho/<pk>/update/", CabecalhoUpdate.as_view(), name='cabecalho_update'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)