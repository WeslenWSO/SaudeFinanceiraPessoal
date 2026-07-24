from django import views
from django.conf.urls.static import static
from django.urls import path
from .views import *
from regrarateio import views

from SaudeFinanceira import settings


app_name = 'regraimposto'

urlpatterns = [
     path("regraList/", RegraImpostoList.as_view(), name='ListaRegra'),
     path("regraAdd/", RegraImpostoCreate.as_view(), name='regraCreate'),
     path("regraUpdate/<int:pk>/", RegraImpostoUpdate.as_view(), name='regraUpdate'),
     path("regraDelete/<int:pk>/", RegraImpostoDelete.as_view(), name='regraDelete'),
        ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)