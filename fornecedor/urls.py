from django.conf.urls.static import static
from django.urls import path
from .views import *

from SaudeFinanceira import settings


app_name = 'fornecedor'

urlpatterns = [

    path("fornList/", FornList.as_view(), name='fornList'),
    # path("cob/<pk>", CobDetail.as_view(), name="cob-detail"),
    path("<pk>/update", FornUpdate.as_view(), name="forn-update"),
    path('forn/create/', FornCreate.as_view(), name='forn-create'),
    path('<int:pk>/delete/', excluir_fornecedor, name='forn-delete'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)