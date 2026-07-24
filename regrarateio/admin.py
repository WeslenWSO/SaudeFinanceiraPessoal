from django.contrib import admin
from .models import LancamentoRateio, RegraRateio, RegraRateioItem

# Register your models here.
class RegraRateioAdmin(admin.ModelAdmin):

    list_display = ('id', 'empresa', 'codigo', 'nomedaregra', 'rateio')
    list_display_links = ('id', 'nomedaregra')
    list_filter = ('empresa',)


    list_per_page = 10
    #search_fields = ('nome')
    # ordering = ('qtanimais')
    
    
    
class RegraRateioItemAdmin(admin.ModelAdmin):
        list_display = ('id', 'regrarateio' ,'socios', 'percRateio')
        list_display_links = ('id', 'socios')

        list_per_page = 10
        # search_fields = ('nome')
        # ordering = ('qtanimais')

admin.site.register(RegraRateioItem, RegraRateioItemAdmin)
admin.site.register(RegraRateio, RegraRateioAdmin)


@admin.register(LancamentoRateio)
class LancamentoRateioAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'empresa',
        'tipo',
        'conta_pagar',
        'conta_receber',
        'data_pagamento',
        'socio',
        'regra_rateio',
        'valor',
    )
    list_filter = ('tipo', 'empresa')
    search_fields = ('descricao',)
    raw_id_fields = ('conta_pagar', 'conta_receber', 'socio', 'regra_rateio')