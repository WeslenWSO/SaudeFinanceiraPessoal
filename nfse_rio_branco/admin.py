from django.contrib import admin
from .models import Company
from .models import PortalCredential

# Register your models here.


# Register your models here.


# Register your models here.
class CompanyAdmin(admin.ModelAdmin):

    list_display = ('id','nome','cnpj','inscricao_municipal')
    list_display_links = ('id','nome', 'cnpj','inscricao_municipal')

    list_per_page = 10

admin.site.register(Company , CompanyAdmin)

class PortalCredentialAdmin(admin.ModelAdmin):

    list_display = ('id','company','usuario','senha')
    list_display_links = ('id','company','usuario','senha')

    list_per_page = 10

admin.site.register(PortalCredential , PortalCredentialAdmin)