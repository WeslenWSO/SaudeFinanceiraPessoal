from django.conf.urls.static import static
from django.urls import path

from .views import *

from SaudeFinanceira import settings


app_name = 'formapgto'

urlpatterns = [
    path("formaList/", FormaPgtoList.as_view(), name='formaList'),
    path("forma/<pk>", FormaDetail.as_view(), name="forma-detail"),
    path("<pk>/update", FormaUpdate.as_view(), name="forma-update"),
    path('forma/create/', FormaCreate.as_view(),name='forma-create'),
    
    ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)