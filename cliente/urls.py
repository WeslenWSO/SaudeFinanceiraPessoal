from django.conf.urls.static import static
from django.urls import path
from .views import *

from SaudeFinanceira import settings


app_name = 'cliente'

urlpatterns = [
    path("cliente/", ClieList.as_view(), name='clieList'),
    path("<pk>/update", ClieUpdate.as_view(), name="clie-update"),
    path('cliente/create/', ClieCreate.as_view(),name='clie-create'),
    path("<pk>/delete/", ClieDelete.as_view(), name="clie-delete"),
   ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)