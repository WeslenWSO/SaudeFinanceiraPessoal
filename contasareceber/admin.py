from django.contrib import admin
from .models import ContaAReceber, BaixaContaAReceber

@admin.register(ContaAReceber)
class ContaAReceberAdmin(admin.ModelAdmin):
    list_display = [
        'nota', 'cliente', 'empresa', 'data_emissao', 'data_vencimento',
        'valor_a_receber', 'status', 'dias_atraso', 'forma_pagamento'
    ]
    list_filter = [
        'empresa', 'status', 'categoria', 'regra_rateio', 'data_emissao',
        'data_vencimento', 'data_recebimento'
    ]
    search_fields = [
        'nota__numero_nota', 'cliente', 'observacao', 'empresa__razao', 'empresa__nome_fantasia'
    ]
    readonly_fields = [
        'data_criacao', 'data_atualizacao', 'dias_atraso'
    ]
    date_hierarchy = 'data_vencimento'

    fieldsets = (
        ('Empresa', {
            'fields': ('empresa',)
        }),
        ('Nota Fiscal', {
            'fields': ('nota',)
        }),
        ('Cliente', {
            'fields': ('cliente',)
        }),
        ('Datas', {
            'fields': ('data_emissao', 'data_vencimento', 'data_recebimento')
        }),
        ('Valores', {
            'fields': ('valor_a_receber',)
        }),
        ('Parcela', {
            'fields': ('parcela',)
        }),
        ('Observações', {
            'fields': ('observacao',)
        }),
        ('Classificação', {
            'fields': ('categoria', 'regra_rateio')
        }),
        ('Recebimento', {
            'fields': ('conta_banco', 'valor_recebido', 'desconto', 'juros', 'tarifas')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Timestamps', {
            'fields': ('data_criacao', 'data_atualizacao'),
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

    def dias_atraso(self, obj):
        return obj.dias_atraso
    dias_atraso.short_description = 'Dias em Atraso'
    dias_atraso.admin_order_field = 'data_vencimento'


@admin.register(BaixaContaAReceber)
class BaixaContaAReceberAdmin(admin.ModelAdmin):
    list_display = [
        'conta_a_receber', 'empresa', 'data_recebimento', 'valor_recebido',
        'tipo_baixa', 'conta_banco'
    ]
    list_filter = [
        'empresa', 'tipo_baixa', 'data_recebimento', 'conta_banco'
    ]
    search_fields = [
        'conta_a_receber__cliente', 'conta_a_receber__nota__numero_nota',
        'observacao', 'empresa__razao'
    ]
    readonly_fields = [
        'data_criacao', 'data_atualizacao'
    ]
    date_hierarchy = 'data_recebimento'

    fieldsets = (
        ('Conta a Receber', {
            'fields': ('conta_a_receber', 'empresa')
        }),
        ('Recebimento', {
            'fields': ('data_recebimento', 'valor_recebido', 'tipo_baixa')
        }),
        ('Ajustes', {
            'fields': ('desconto', 'juros', 'tarifas')
        }),
        ('Conta Bancária', {
            'fields': ('conta_banco',)
        }),
        ('Observações', {
            'fields': ('observacao',)
        }),
        ('Timestamps', {
            'fields': ('data_criacao', 'data_atualizacao'),
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
