# nfse_rio_branco/urls.py
from django.urls import path
from .views import start1, status_view

app_name = "nfse_rio_branco"

urlpatterns = [
  #path("start/", StartDownloadView.as_view(), name="start"),
  #path("start/", start1, name="start"),
    path('nfse_download/iniciar/', start1, name='iniciar'),   # <- use "iniciar"
    # (se quiser aceitar /start/ também)
    path('nfse_download/start/', start1, name='start'),
    path('nfse_download/status/', status_view, name='status'),
]