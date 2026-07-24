from django.conf.urls.static import static
from django.urls import re_path as url
from SaudeFinanceira import settings
from dashboard import views


app_name = 'dashboard'

urlpatterns = [
    url(r'^resumo-fechamento/?$', views.resumo_fechamento, name='resumo_fechamento'),
    url(r'^relatorio-mensal/?$', views.relatorio_mensal, name='relatorio_mensal'),
    url(r'^$', views.dashboard_inicio, name='index'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)