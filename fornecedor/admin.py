from django.contrib import admin
from .models import Fornecedor, SocioFornecedor


class SocioFornecedorInline(admin.TabularInline):
    model = SocioFornecedor
    extra = 0


# Register your models here.
class FornecedorAdmin(admin.ModelAdmin):

    list_display = ('id', 'razao', 'codigo_externo', 'cnpj', 'telefone')
    list_display_links = ('id', 'razao', 'cnpj', 'telefone')
    inlines = [SocioFornecedorInline]

    list_per_page = 10
    #search_fields = ('nome')
    # ordering = ('qtanimais')


admin.site.register(Fornecedor, FornecedorAdmin)