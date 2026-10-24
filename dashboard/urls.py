from django.conf.urls.static import static
from django.urls import re_path as url
from SaudeFinanceira import settings
from dashboard import views
from dashboard.conta_azul_views import (
    analises_relatorio_apresentacao,
    analises_relatorio_download,
    analises_relatorio_pdf,
    analises_relatorio_whatsapp,
    conta_azul_dashboard,
    conta_azul_dashboard_por_tipo,
    conta_azul_sincronizar_dashboard,
)


app_name = 'dashboard'

urlpatterns = [
    url(r'^resumo-fechamento/?$', views.resumo_fechamento, name='resumo_fechamento'),
    url(
        r'^resumo-fechamento-por-resultado/?$',
        views.resumo_fechamento_por_resultado,
        name='resumo_fechamento_por_resultado',
    ),
    url(r'^relatorio-mensal/?$', views.relatorio_mensal, name='relatorio_mensal'),
    url(r'^por-tipo/?$', conta_azul_dashboard_por_tipo, name='por_tipo'),
    url(r'^conta-azul/sincronizar-rapido/?$', conta_azul_sincronizar_dashboard, name='conta_azul_sync_rapido'),
    url(r'^conta-azul/?$', conta_azul_dashboard, name='conta_azul'),
    url(r'^analises/relatorio/?$', analises_relatorio_apresentacao, name='analises_relatorio'),
    url(r'^analises/relatorio\.pdf/?$', analises_relatorio_pdf, name='analises_relatorio_pdf'),
    url(
        r'^analises/relatorio/download/(?P<token>[a-f0-9]{32})/?$',
        analises_relatorio_download,
        name='analises_relatorio_download',
    ),
    url(r'^analises/relatorio/whatsapp/?$', analises_relatorio_whatsapp, name='analises_relatorio_whatsapp'),
    url(r'^$', conta_azul_dashboard, name='index'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)