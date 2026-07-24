from django.urls import path
from . import views

app_name = 'regraConciliacao'

urlpatterns = [
    path('', views.RegraConciliacaoList.as_view(), name='regraList'),
    path('create/', views.RegraConciliacaoCreate.as_view(), name='regraCreate'),
    path('<int:pk>/update/', views.RegraConciliacaoUpdate.as_view(), name='regraUpdate'),
    path('<int:pk>/delete/', views.RegraConciliacaoDelete.as_view(), name='regraDelete'),
]