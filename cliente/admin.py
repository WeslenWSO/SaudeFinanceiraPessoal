from django.contrib import admin
from .models import Cliente

# Register your models here.
class ClienteAdmin(admin.ModelAdmin):

    list_display = ('id', 'razao', 'codigo_externo', 'cnpj', 'telefone', 'descricao_extrato_bancario')
    list_display_links = ('id', 'razao', 'cnpj', 'telefone')


    list_per_page = 10
    #search_fields = ('nome')
    # ordering = ('qtanimais')


admin.site.register(Cliente, ClienteAdmin)