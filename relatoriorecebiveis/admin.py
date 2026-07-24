from django.contrib import admin
from .models import RelatorioRecebiveisMaquinaCartao

@admin.register(RelatorioRecebiveisMaquinaCartao)
class RelatorioRecebiveisMaquinaCartaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'data_pagamento','data_venda','empresa','parcelas','total_parcelas','forma_pagamento', 'bandeira', 'valor_bruto', 'taxa_maquinha', 'valor_liquido', 'maquinha', 'numero_autorizacao', 'conta_bancaria')
    list_filter = ('data_pagamento', 'forma_pagamento', 'bandeira', 'maquinha', 'conciliado')
    search_fields = ('numero_autorizacao', 'nota_fiscal', 'razao')
    ordering = ('-data_pagamento',)
    readonly_fields = ('taxa_perc',)
