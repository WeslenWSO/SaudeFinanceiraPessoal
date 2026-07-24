from django.contrib import admin
from .models import FaturamentoMedico


@admin.register(FaturamentoMedico)
class FaturamentoMedicoAdmin(admin.ModelAdmin):
    """Admin para Faturamento Médico"""

    # Campos exibidos na lista
    list_display = [
        'nome', 'guia', 'servico', 'data', 'total', 'convenio',
        'medico', 'guia_lancada', 'data_criacao'
    ]

    # Campos de busca
    search_fields = [
        'nome', 'guia', 'carteirinha', 'servico', 'codigo_servico',
        'medico', 'anestesista', 'convenio', 'receber_por'
    ]

    # Filtros laterais
    list_filter = [
        'data', 'data_autorizacao', 'convenio', 'porte', 'local',
        'guia_lancada', 'data_criacao', 'data_atualizacao'
    ]

    # Campos readonly
    readonly_fields = ['data_criacao', 'data_atualizacao']

    # Ordenação padrão
    ordering = ['-data', '-data_criacao']

    # Campos organizados em fieldsets
    fieldsets = (
        ('Informações Principais', {
            'fields': (
                'empresa', 'lote', 'guia', 'carteirinha', 'nome',
                'codigo_servico', 'servico'
            )
        }),
        ('Datas', {
            'fields': ('data_autorizacao', 'data')
        }),
        ('Valores', {
            'fields': ('porte', 'qt', 'valor', 'total')
        }),
        ('Profissionais', {
            'fields': ('local', 'medico', 'anestesista')
        }),
        ('Outros', {
            'fields': (
                'convenio', 'receber_por', 'observacao',
                'guia_lancada', 'codigo_relatorio'
            )
        }),
        ('Timestamps', {
            'fields': ('data_criacao', 'data_atualizacao'),
            'classes': ('collapse',)
        }),
    )

    # Configurações adicionais
    list_per_page = 25
    date_hierarchy = 'data'
