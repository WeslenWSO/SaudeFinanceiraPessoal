from django.conf.urls.static import static
from django.urls import path


from SaudeFinanceira import settings
from usuario import views

app_name = 'usuario'

urlpatterns = [

    path('usuario/', views.listaUsuario, name='usuarioList'),
    path('usuario/create/', views.UsuarioCreate.as_view(), name='usuario-create'),
    path('usuario/<pk>/update/', views.UsuarioUpdate.as_view(), name='usuario-update'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)