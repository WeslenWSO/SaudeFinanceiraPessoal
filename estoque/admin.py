from django.contrib import admin

from estoque.models import ProdutoEstoque, SetorEstoqueResponsavel


@admin.register(ProdutoEstoque)
class ProdutoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        'codigo_produto',
        'descricao',
        'marca',
        'quantidade_estoque',
        'quantidade_estoque_contabil',
        'valor_custo_medio',
        'empresa',
    )
    list_filter = ('empresa', 'marca')
    search_fields = ('codigo_produto', 'descricao', 'marca')


@admin.register(SetorEstoqueResponsavel)
class SetorEstoqueResponsavelAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'setor', 'usuario')
    list_filter = ('empresa', 'setor')
