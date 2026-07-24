from django.conf.urls.static import static
from django.urls import path
from .views import *

from SaudeFinanceira import settings


app_name = 'cobranca'

urlpatterns = [

    path("cobList/", CobList.as_view(), name='cobList'),
    # path("cob/<pk>", CobDetail.as_view(), name="cob-detail"),
    path("<pk>/update", CobUpdate.as_view(), name="cob-update"),
    path('cob/create/', CobCreate.as_view(),name='cob-create'),
        ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)