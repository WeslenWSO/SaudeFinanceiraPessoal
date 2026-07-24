from django.contrib import admin

from .models import ItemOrcamento, LancamentoOrcamento


class LancamentoInline(admin.TabularInline):
    model = LancamentoOrcamento
    extra = 0
    readonly_fields = ('data_lancamento', 'valor', 'sequencia', 'criado_em')
    can_delete = False


@admin.register(ItemOrcamento)
class ItemOrcamentoAdmin(admin.ModelAdmin):
    list_display = (
        'nome', 'categoria', 'tipo', 'empresa', 'forma_calculo',
        'valor_mensal', 'data_inicio', 'qtd_meses', 'ativo', 'ordem',
    )
    list_filter = ('tipo', 'forma_calculo', 'ativo', 'empresa')
    search_fields = ('nome', 'observacao', 'categoria__nome')
    raw_id_fields = ('categoria',)
    ordering = ('empresa', 'tipo', 'ordem', 'nome')
    inlines = [LancamentoInline]


@admin.register(LancamentoOrcamento)
class LancamentoOrcamentoAdmin(admin.ModelAdmin):
    list_display = ('item', 'empresa', 'data_lancamento', 'valor', 'sequencia')
    list_filter = ('empresa', 'data_lancamento')
    search_fields = ('item__nome',)
    date_hierarchy = 'data_lancamento'
