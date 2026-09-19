from django.contrib import admin

from inventario.models import Inventario, InventarioItem, InventarioResponsavelContagem


class InventarioItemInline(admin.TabularInline):
    model = InventarioItem
    extra = 0
    readonly_fields = (
        'codigo_produto',
        'descricao_produto',
        'quantidade_estoque',
        'contagem_1_em',
        'contagem_1_por',
        'contagem_2_em',
        'contagem_2_por',
        'contagem_3_em',
        'contagem_3_por',
    )


class ResponsavelInline(admin.TabularInline):
    model = InventarioResponsavelContagem
    extra = 0


@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'empresa', 'aberto', 'criado_em', 'criado_por')
    list_filter = ('aberto', 'empresa')
    inlines = (ResponsavelInline, InventarioItemInline)
