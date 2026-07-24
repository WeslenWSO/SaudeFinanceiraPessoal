from django.conf.urls.static import static
from django.urls import path

from . import views

from SaudeFinanceira import settings


app_name = 'notafiscalentrada'

urlpatterns = [
    path('', views.listar_notas_fiscais, name='listar'),
    path('importar/', views.importar_xml, name='importar'),
    path('editar/<int:pk>/', views.editar_nota_fiscal, name='editar'),
    path('excluir/<int:pk>/', views.excluir_nota_fiscal, name='excluir'),
    path('aplicar_categoria/', views.aplicar_categoria, name='aplicar_categoria'),
    path('aplicar_forma_pagamento/', views.aplicar_forma_pagamento, name='aplicar_forma_pagamento'),
    path('gerar_contas_a_pagar/', views.gerar_contas_a_pagar, name='gerar_contas_a_pagar'),
    path('buscar_categorias/', views.buscar_categorias, name='buscar_categorias'),
    path('buscar_formas_pagamento/', views.buscar_formas_pagamento, name='buscar_formas_pagamento'),
    path('detalhes/<str:tipo>/<int:id>/', views.detalhes_modal, name='detalhes_modal'),
    ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)