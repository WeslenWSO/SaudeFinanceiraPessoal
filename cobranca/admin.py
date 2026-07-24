from django.contrib import admin

# Register your models here.
from cobranca.models import Cobranca

# Register your models here.
class CobrancaAdmin(admin.ModelAdmin):

    list_display = ('id','descricao','tpag')
    list_display_links = ('id', 'descricao','tpag')

    list_per_page = 10

admin.site.register(Cobranca , CobrancaAdmin)