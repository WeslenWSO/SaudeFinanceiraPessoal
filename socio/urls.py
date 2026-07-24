from django.conf.urls.static import static
from django.urls import path


from SaudeFinanceira import settings
from socio import views
from .views import *

app_name = 'socio'

urlpatterns = [
    path('socio/', views.listaSocio, name='socList'),
    path('', views.Tela_Cad, name='Tela_Cad'),
    path('socio_CadAlt/', views.soc_Cad_Alt, name='Tela_Alt_Cad'),
   # path('<pk>/edit', views.SocioUpdateView.as_view(), name='soc_img_alt'),
    # path('AltImg/<int:pk>', views.SocioUpdateView.as_view(), name='soc_img_alt'),
    path('AltImg/<int:pk>', views.soc_Img, name='soc_img_alt'),
   
    #path('soc_Busca/', views.busca, name='soc_Busca'),
    path('soc_CadTelEd/<int:pk>', views.soc_CadTelEd, name='soc_CadTelEd'),
    
    #path('soc_Cad_Alt/', views.soc_Cad_Alt, name='soc_Cad_Alt'),
    #path('soc_ver/<int:soc_id>', views.ver_socio, name='ver_socio'),
    path('soc_Cad/', views.soc_Cad, name='soc_Cad'),
    path('soc_CadExcluir/<int:soc_id>', views.soc_CadExcluir, name='soc_CadExcluir'),


] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
