from django.contrib import admin

from OPCARTAO.models import CartaoCredito, FaturaCartaoCredito, ItemFaturaCartao, Opcartao


class ItemFaturaCartaoInline(admin.TabularInline):
    model = ItemFaturaCartao
    extra = 0
    readonly_fields = ('data', 'hora', 'descricao', 'valor', 'tipo', 'parcela')


@admin.register(CartaoCredito)
class CartaoCreditoAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'empresa', 'descricao', 'banco', 'bandeira', 'limite', 'final_cartao',
        'dia_fechamento_fatura', 'dia_vencimento_fatura', 'ativo',
    )
    list_filter = ('banco', 'bandeira', 'ativo')
    search_fields = ('descricao', 'final_cartao')


@admin.register(FaturaCartaoCredito)
class FaturaCartaoCreditoAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'cartao', 'banco', 'vencimento', 'total_fatura', 'cartao_final', 'importado_em')
    list_filter = ('banco', 'vencimento')
    search_fields = ('titular', 'cartao_final', 'arquivo_nome')
    inlines = [ItemFaturaCartaoInline]


class OpCartaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'descricao', 'tband')
    list_display_links = ('id', 'descricao', 'tband')
    list_per_page = 10


admin.site.register(Opcartao, OpCartaoAdmin)
