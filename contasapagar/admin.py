from django.contrib import admin
from contasapagar.models import ContasaPagar


class ContasaPagarAdmin(admin.ModelAdmin):
        list_display = ('id', 'descricao' ,'valorDoc', 'dtEmissao', 'parcela', 'rateio', 'cobranca')
        list_display_links = ('id', 'descricao')

        list_per_page = 10
        # search_fields = ('nome')
        # ordering = ('qtanimais')

admin.site.register(ContasaPagar, ContasaPagarAdmin)