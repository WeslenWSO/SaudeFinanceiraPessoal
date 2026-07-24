from django.conf.urls.static import static
from django.urls import path
from django.conf import settings
from .views import (
    lista_empresas,
    selecionar_empresa,
    selecionar_empresa_ajax,
    trocar_empresa,
    empresa_atual,
    buscar_empresa_por_cnpj_ajax,
    certificados_windows_por_cnpj,
    certificados_windows_por_empresa_sessao,
    empresa_create,
    empresa_update,
    empresa_detail,
    empresa_toggle_status,
    empresa_sucesso,
    empresa_integracao,
)

app_name = 'empresa'

urlpatterns = [
    path('lista/', lista_empresas, name='lista'),
    path('api/buscar-cnpj/', buscar_empresa_por_cnpj_ajax, name='buscar_cnpj_ajax'),
    path(
        'api/certificados-windows-cnpj/',
        certificados_windows_por_cnpj,
        name='certificados_windows_por_cnpj',
    ),
    path(
        'api/certificados-windows/',
        certificados_windows_por_empresa_sessao,
        name='certificados_windows_sessao',
    ),
    path('selecionar/<int:empresa_id>/', selecionar_empresa, name='selecionar'),
    path('selecionar-ajax/', selecionar_empresa_ajax, name='selecionar_ajax'),
    path('trocar/', trocar_empresa, name='trocar'),
    path('atual/', empresa_atual, name='atual'),
    path('nova/', empresa_create, name='empresa_create'),
    path('<int:pk>/editar/', empresa_update, name='empresa_edit'),
    path('<int:pk>/configuracao-integracao/', empresa_integracao, name='empresa_integracao'),
    path('<int:pk>/detalhe/', empresa_detail, name='empresa_detail'),
    path('<int:pk>/toggle-status/', empresa_toggle_status, name='empresa_toggle_status'),
    path('sucesso/', empresa_sucesso, name='empresa_sucesso'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)