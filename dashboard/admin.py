from django.contrib import admin

from dashboard.conta_azul_forms import ContaAzulConfigForm
from dashboard.models import ContaAzulConfig


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
