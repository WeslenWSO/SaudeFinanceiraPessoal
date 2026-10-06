from django.contrib import admin

from orcamento_compra.models import (
    OrcamentoCompra,
    OrcamentoCompraFornecedor,
    OrcamentoCompraItem,
    OrcamentoCompraPreco,
    OrcamentoCompraResultadoVencedor,
    OrcamentoCompraResultadoVencedorItem,
)


class ItemInline(admin.TabularInline):
    model = OrcamentoCompraItem
    extra = 0


class FornecedorInline(admin.TabularInline):
    model = OrcamentoCompraFornecedor
    extra = 0


@admin.register(OrcamentoCompra)
class OrcamentoCompraAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'empresa', 'status', 'atualizado_em')
    list_filter = ('status', 'empresa')
    search_fields = ('titulo',)
    inlines = [ItemInline, FornecedorInline]


admin.site.register(OrcamentoCompraPreco)
admin.site.register(OrcamentoCompraResultadoVencedor)
admin.site.register(OrcamentoCompraResultadoVencedorItem)
