from django.contrib import admin
from .models import Empresa, UsuarioEmpresa

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = [
        'razao', 'nome_fantasia', 'cnpj', 'codigo_externo', 'status', 'regime_tributario', 'anexo_i', 'anexo_ii', 'anexo_iii', 'anexo_iv', 'anexo_v', 'tem_fator_r', 'tipo_apuracao', 'data_criacao'
    ]
    list_filter = [
        'status', 'regime_tributario', 'anexo_i', 'anexo_ii', 'anexo_iii', 'anexo_iv', 'anexo_v', 'tem_fator_r', 'tipo_apuracao', 'data_criacao'
    ]
    search_fields = [
        'razao', 'nome_fantasia', 'cnpj', 'codigo_externo'
    ]
    readonly_fields = [
        'data_criacao', 'data_atualizacao'
    ]
    ordering = ['razao']
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('razao', 'nome_fantasia', 'cnpj', 'codigo_externo', 'status')
        }),
        ('Configurações Fiscais', {
            'fields': ('regime_tributario', 'anexo_i', 'anexo_ii', 'anexo_iii', 'anexo_iv', 'anexo_v', 'tem_fator_r', 'tipo_apuracao', 'usa_base_calculo_reduzido', 'utiliza_iss_fixo')
        }),
        ('Contato', {
            'fields': ('endereco', 'telefone', 'email')
        }),
        ('Cópia em disco — XML NFSe importado', {
            'fields': (
                'nfse_nacional_codigo_ibge_municipio',
                'nfse_nacional_dps_serie_padrao',
                'nfse_nacional_dps_proximo_numero',
                'nfse_xml_pasta_prestador',
                'nfse_xml_pasta_tomador',
            ),
            'classes': ('collapse',),
            'description': (
                'IBGE de 7 dígitos pré-preenche consulta DPS no portal. Após importar ou baixar do portal, '
                'o sistema grava XML (e PDF se a API devolver) em subpastas código_externo-razão / competência (MMYYYY) / [Cancelada/]. '
                'Emitida (empresa prestadora no XML) → pasta prestador; recebida (tomadora) → pasta tomador.'
            ),
        }),
        ('Timestamps', {
            'fields': ('data_criacao', 'data_atualizacao'),
            'classes': ('collapse',)
        }),
    )

@admin.register(UsuarioEmpresa)
class UsuarioEmpresaAdmin(admin.ModelAdmin):
    list_display = [
        'usuario', 'empresa', 'ativo', 'data_criacao'
    ]
    list_filter = [
        'ativo', 'empresa', 'data_criacao'
    ]
    search_fields = [
        'usuario__username', 'usuario__first_name', 'usuario__last_name', 'empresa__razao'
    ]
    readonly_fields = [
        'data_criacao'
    ]
    ordering = ['usuario', 'empresa']
    
    fieldsets = (
        ('Usuário e Empresa', {
            'fields': ('usuario', 'empresa', 'ativo')
        }),
        ('Timestamps', {
            'fields': ('data_criacao',),
            'classes': ('collapse',)
        }),
    )