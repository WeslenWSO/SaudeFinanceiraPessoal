from django.contrib import admin

from inventario.models import (
    EstoqueBackup,
    EstoqueBackupLinha,
    Inventario,
    InventarioItem,
    InventarioResponsavelContagem,
)


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
    list_display = (
        'descricao',
        'empresa',
        'aberto',
        'rodada_atualiza_estoque',
        'criado_em',
        'criado_por',
    )
    list_filter = ('aberto', 'empresa')
    inlines = (ResponsavelInline, InventarioItemInline)


@admin.register(EstoqueBackup)
class EstoqueBackupAdmin(admin.ModelAdmin):
    list_display = ('inventario', 'empresa', 'criado_em', 'criado_por')
    list_filter = ('empresa',)


@admin.register(EstoqueBackupLinha)
class EstoqueBackupLinhaAdmin(admin.ModelAdmin):
    list_display = ('backup', 'codigo_produto', 'quantidade_estoque')
    search_fields = ('codigo_produto',)
