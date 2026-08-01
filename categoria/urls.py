from django.conf.urls.static import static
from django.urls import path
from .views import *

from SaudeFinanceira import settings


app_name = 'categoria'

urlpatterns = [

    path("catList/", CatList.as_view(), name='catList'),
    # path("cob/<pk>", CobDetail.as_view(), name="cob-detail"),
    path("<pk>/update", CatUpdate.as_view(), name="cat-update"),
    path('cat/create/', CatCreate.as_view(),name='cat-create'),
    path('<pk>/delete/', CatDelete.as_view(), name='cat-delete'),
    path('copiar/', copiar_categorias, name='copiar'),
    path('grupos-empresa/', grupos_empresa, name='grupos_empresa'),
        ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)