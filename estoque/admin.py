from django.contrib import admin

from estoque.models import ProdutoEstoque


@admin.register(ProdutoEstoque)
class ProdutoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        'codigo_produto',
        'descricao',
        'marca',
        'quantidade_estoque',
        'valor_custo_medio',
        'empresa',
    )
    list_filter = ('empresa', 'marca')
    search_fields = ('codigo_produto', 'descricao', 'marca')
