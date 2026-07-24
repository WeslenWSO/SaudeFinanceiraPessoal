from django.contrib import admin
from .models import NotaFiscalServico, FolhaSalario

@admin.register(NotaFiscalServico)
class NotaFiscalServicoAdmin(admin.ModelAdmin):
    actions = ['apagar_selecionados_provisorio']

    list_display = [
        'numero_nota', 'serie', 'cliente', 'empresa', 'socio', 'data_emissao',
        'valor_liquido', 'iss_retido', 'forma_pagamento','nsu', 'status_conciliacao', 'codigo_da_regra_do_imposto',
    ]
    list_filter = [
        'empresa', 'socio', 'status_conciliacao', 'forma_pagamento','nsu', 'data_emissao',
         'serie', 'iss_retido'
    ]
    search_fields = [
        'numero_nota', 'cliente', 'cnpj_cpf', 'discriminacao', 'empresa__razao', 'empresa__nome_fantasia'
    ]
    readonly_fields = [
        'data_criacao', 'data_atualizacao'
    ]
    date_hierarchy = 'data_emissao'
    
    fieldsets = (
        ('Empresa', {
            'fields': ('empresa',)
        }),
        ('Informações da Nota', {
            'fields': ('numero_nota', 'serie', 'data_emissao')
        }),
        ('Cliente', {
            'fields': ('cnpj_cpf', 'cliente')
        }),
        ('Valores', {
            'fields': ('valor_bruto', 'valor_liquido')
        }),
        ('Impostos e Retenções', {
            'fields': (
                'valor_deducoes', 'valor_pis', 'valor_cofins', 'valor_inss',
                'valor_ir', 'valor_csll', 'iss_retido', 
                'valor_iss_retido', 'outras_retencoes', 'aliquota', 'codigo_da_regra_do_imposto'
            ),
            'classes': ('collapse',)
        }),
        ('Sócio Responsável', {
            'fields': ('socio',)
        }),
        ('Detalhes', {
            'fields': ('discriminacao', 'observacoes')
        }),
        ('Cancelamento', {
            'fields': ('data_cancelamento',)
        }),
        ('Pagamento', {
            'fields': ('forma_pagamento', 'nsu')
        }),
        
        ('Status', {
            'fields': ('status_conciliacao',)
        }),
        ('Timestamps', {
            'fields': ('data_criacao', 'data_atualizacao'),
            'classes': ('collapse',)
        }),
        ('Impostos e Apuracao', {
            'fields': ( 'pisapuracao', 'cofinsapuracao', 'csllapuracao', 'irpjapuracao'),
            'classes': ('collapse',)
        }),
        
    )
    
    def get_queryset(self, request):
        """Filtra por empresa se o usuário não for superuser"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Aqui você pode implementar lógica para filtrar por empresa do usuário
        return qs
    
    def valor_pendente(self, obj):
        return obj.get_valor_pendente()
    valor_pendente.short_description = 'Valor Pendente'
    
    def is_pago(self, obj):
        return obj.is_pago()
    is_pago.boolean = True
    is_pago.short_description = 'Pago'
    
    def is_cancelada(self, obj):
        return obj.is_cancelada()
    is_cancelada.boolean = True
    is_cancelada.short_description = 'Cancelada'

    @admin.action(description='Apagar selecionados (provisório)')
    def apagar_selecionados_provisorio(self, request, queryset):
        n = queryset.count()
        queryset.delete()
        self.message_user(request, f'{n} registro(s) apagado(s) da tabela Notas Fiscais de Serviço (provisório).')


@admin.register(FolhaSalario)
class FolhaSalarioAdmin(admin.ModelAdmin):
    list_display = ['empresa', 'ano', 'mes', 'total_salario']
    list_filter = ['empresa', 'ano', 'mes']
    search_fields = ['empresa__razao', 'empresa__nome_fantasia']
    ordering = ['empresa', 'ano', 'mes']

    fieldsets = (
        ('Empresa', {
            'fields': ('empresa',)
        }),
        ('Período', {
            'fields': ('ano', 'mes')
        }),
        ('Valor', {
            'fields': ('total_salario',)
        }),
    )
