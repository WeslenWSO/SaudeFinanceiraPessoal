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
from dashboard.conta_azul_views import (
    conta_azul_config,
    conta_azul_desconectar,
    conta_azul_oauth_callback,
    conta_azul_oauth_dev,
    conta_azul_oauth_dev_captura,
    conta_azul_oauth_iniciar,
    conta_azul_sincronizar,
    conta_azul_testar,
    conta_azul_trocar_codigo,
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
    path('<int:pk>/conta-azul/', conta_azul_config, name='conta_azul_config'),
    path('<int:pk>/conta-azul/sincronizar/', conta_azul_sincronizar, name='conta_azul_sincronizar'),
    path('<int:pk>/conta-azul/oauth/iniciar/', conta_azul_oauth_iniciar, name='conta_azul_oauth_iniciar'),
    path('<int:pk>/conta-azul/oauth/dev/', conta_azul_oauth_dev, name='conta_azul_oauth_dev'),
    path('conta-azul/oauth/dev/captura/', conta_azul_oauth_dev_captura, name='conta_azul_oauth_dev_captura'),
    path('<int:pk>/conta-azul/desconectar/', conta_azul_desconectar, name='conta_azul_desconectar'),
    path('<int:pk>/conta-azul/trocar-codigo/', conta_azul_trocar_codigo, name='conta_azul_trocar_codigo'),
    path('<int:pk>/conta-azul/testar/', conta_azul_testar, name='conta_azul_testar'),
    path('conta-azul/oauth/callback/', conta_azul_oauth_callback, name='conta_azul_oauth_callback'),
    path('<int:pk>/detalhe/', empresa_detail, name='empresa_detail'),
    path('<int:pk>/toggle-status/', empresa_toggle_status, name='empresa_toggle_status'),
    path('sucesso/', empresa_sucesso, name='empresa_sucesso'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)