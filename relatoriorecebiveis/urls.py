from django.urls import path
from . import views

app_name = 'relatoriorecebiveis'

urlpatterns = [
    path('', views.relatorio_recebiveis_list, name='relReclist'),
    path('create/', views.relatorio_recebiveis_create, name='create'),
    path('import-csv/', views.relatorio_recebiveis_import_csv, name='import_csv'),
    path(
        'import-pdf-infinitepay/',
        views.relatorio_recebiveis_import_pdf_infinitepay,
        name='import_pdf_infinitepay',
    ),
    path(
        'import-xlsx-cielo/',
        views.relatorio_recebiveis_import_xlsx_cielo,
        name='import_xlsx_cielo',
    ),
    path('conciliate/', views.relatorio_recebiveis_conciliate, name='conciliate'),
    path('<int:pk>/', views.relatorio_recebiveis_detail, name='detail'),
    path('<int:pk>/update/', views.relatorio_recebiveis_update, name='update'),
    path('<int:pk>/delete/', views.relatorio_recebiveis_delete, name='delete'),
]