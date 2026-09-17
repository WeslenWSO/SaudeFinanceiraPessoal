from django.contrib import admin

from dashboard.conta_azul_forms import ContaAzulConfigForm
from dashboard.models import ContaAzulConfig, GeminiConfig, ServicoContaAzul


@admin.register(ContaAzulConfig)
class ContaAzulConfigAdmin(admin.ModelAdmin):
    form = ContaAzulConfigForm
    list_display = (
        'empresa',
        'ambiente',
        'ativo',
        'credenciais_ok',
        'conectado_ok',
        'token_expira_em',
        'atualizado_em',
    )
    list_filter = ('ambiente', 'ativo')
    search_fields = ('empresa__razao', 'client_id')
    readonly_fields = ('conectado_em', 'criado_em', 'atualizado_em', 'token_expira_em')

    def credenciais_ok(self, obj):
        return obj.credenciais_preenchidas()

    credenciais_ok.boolean = True

    def conectado_ok(self, obj):
        return obj.tem_refresh_token()

    conectado_ok.boolean = True


@admin.register(ServicoContaAzul)
class ServicoContaAzulAdmin(admin.ModelAdmin):
    list_display = (
        'codigo',
        'descricao',
        'empresa',
        'c_class_trib',
        'codigo_nbs',
        'fiscal_pendente_envio',
        'atualizado_em',
    )
    list_filter = ('fiscal_pendente_envio', 'empresa')
    search_fields = ('codigo', 'descricao', 'conta_azul_id')
    readonly_fields = (
        'aliquota_ibs',
        'aliquota_ibs_municipal',
        'aliquota_cbs',
        'importado_em',
        'enviado_em',
        'criado_em',
        'atualizado_em',
    )


@admin.register(GeminiConfig)
class GeminiConfigAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'chave_ok', 'atualizado_em')
    readonly_fields = ('atualizado_em',)

    def chave_ok(self, obj):
        return obj.api_key_configurada()

    chave_ok.boolean = True
    chave_ok.short_description = 'API Key'

    def has_add_permission(self, request):
        return not GeminiConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
