from django.conf.urls.static import static
from django.urls import path





from SaudeFinanceira import settings
from accounts import views




app_name = 'accounts'

urlpatterns = [
         path('', views.login_view ,  name='login'), 
         path('login/', views.login_view ,  name='login'),
         path('logout/', views.logout_view ,name='logout')
         
    ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)