from django.contrib import admin

from .models import Emprestimo, IndicadorCalculoSicoob, ParcelaEmprestimo, SimulacaoQuitacaoEmprestimo


@admin.register(IndicadorCalculoSicoob)
class IndicadorCalculoSicoobAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'rotulo', 'nome', 'tipo', 'ativo')
    list_filter = ('tipo', 'ativo')
    search_fields = ('rotulo', 'nome', 'codigo')


class ParcelaEmprestimoInline(admin.TabularInline):
    model = ParcelaEmprestimo
    extra = 0
    fields = (
        'numero', 'data_vencimento', 'valor_parcela', 'amortizacao', 'juros',
        'data_pagamento', 'valor_pago', 'correcao', 'status',
    )
    readonly_fields = fields
    can_delete = False


@admin.register(Emprestimo)
class EmprestimoAdmin(admin.ModelAdmin):
    list_display = (
        'numero_contrato', 'empresa', 'banco', 'cliente', 'valor_contrato',
        'indicador', 'taxa_juros_am', 'data_operacao',
    )
    list_filter = ('empresa', 'banco', 'indicador', 'indicador__tipo')
    search_fields = ('numero_contrato', 'cliente', 'cooperativa')
    autocomplete_fields = ('indicador', 'banco')
    inlines = [ParcelaEmprestimoInline]


@admin.register(ParcelaEmprestimo)
class ParcelaEmprestimoAdmin(admin.ModelAdmin):
    list_display = (
        'emprestimo', 'numero', 'data_vencimento', 'valor_parcela',
        'amortizacao', 'juros', 'data_pagamento', 'status',
    )
    list_filter = ('status', 'emprestimo__empresa')
    search_fields = ('emprestimo__numero_contrato',)


@admin.register(SimulacaoQuitacaoEmprestimo)
class SimulacaoQuitacaoEmprestimoAdmin(admin.ModelAdmin):
    list_display = (
        'emprestimo', 'titulo', 'data_quitacao', 'valor_quitacao',
        'qtd_parcelas', 'metodo', 'criado_em',
    )
    list_filter = ('metodo', 'emprestimo__empresa')
    search_fields = (
        'titulo', 'emprestimo__numero_contrato', 'emprestimo__cliente',
        'parcelas_numeros',
    )
    readonly_fields = ('criado_em',)
