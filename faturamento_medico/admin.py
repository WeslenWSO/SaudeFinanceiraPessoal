from django.contrib import admin
from .models import (
    ApelidoSolicitante,
    FaturamentoMedico,
    LogStatusConferenciaItem,
    MedcloudConfig,
    MedcloudConvenioParceiro,
)
from .medcloud.config import credenciais_da_empresa, gravar_api_key_his, gravar_senha_ris
from .medcloud_admin_form import MedcloudConfigAdminForm


class MedcloudConvenioParceiroInline(admin.TabularInline):
    model = MedcloudConvenioParceiro
    extra = 1
    fields = ('convenio_nome', 'partner_id', 'exige_laudo')


@admin.register(MedcloudConfig)
class MedcloudConfigAdmin(admin.ModelAdmin):
    form = MedcloudConfigAdminForm
    list_display = ('empresa', 'ativo', 'ris_username', 'ris_clinic_id', 'credenciais_ris_ok', 'his_configurado')
    list_filter = ('ativo',)
    inlines = [MedcloudConvenioParceiroInline]
    fieldsets = (
        (None, {'fields': ('empresa', 'ativo')}),
        ('RIS — Agendamentos', {
            'fields': (
                'ris_base_url', 'ris_username', 'ris_senha', 'ris_clinic_id',
                'ris_lista_agendas_path',
            ),
        }),
        ('HIS — Laudos', {
            'fields': ('his_base_url', 'his_api_key'),
        }),
    )

    def save_model(self, request, obj, form, change):
        senha = form.cleaned_data.get('ris_senha')
        if senha:
            gravar_senha_ris(obj, senha)
        api_key = form.cleaned_data.get('his_api_key')
        if api_key:
            gravar_api_key_his(obj, api_key)
        super().save_model(request, obj, form, change)

    @admin.display(boolean=True, description='RIS OK')
    def credenciais_ris_ok(self, obj):
        creds = credenciais_da_empresa(obj.empresa)
        return bool(creds and creds.ris_username and creds.ris_password and creds.ris_clinic_id)

    @admin.display(boolean=True, description='HIS OK')
    def his_configurado(self, obj):
        creds = credenciais_da_empresa(obj.empresa)
        return bool(creds and creds.his_api_key)


@admin.register(ApelidoSolicitante)
class ApelidoSolicitanteAdmin(admin.ModelAdmin):
    list_display = ('apelido', 'grafia', 'empresa')
    list_filter = ('empresa',)
    search_fields = ('apelido', 'grafia')
    ordering = ('apelido', 'grafia')


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


@admin.register(LogStatusConferenciaItem)
class LogStatusConferenciaItemAdmin(admin.ModelAdmin):
    list_display = ('data_hora', 'usuario_nome', 'status_conferencia', 'item_servico')
    list_filter = ('status_conferencia',)
    search_fields = ('usuario_nome', 'status_conferencia', 'item_servico__servico')
    readonly_fields = ('item_servico', 'usuario', 'usuario_nome', 'status_conferencia', 'data_hora')
    date_hierarchy = 'data_hora'
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
