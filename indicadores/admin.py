from django.contrib import admin

from .models import (
    AtendenteAcademia,
    Indicador,
    ItemAtendenteDiario,
    ItemPeriodoAcademia,
    LancamentoVendasDiario,
    PeriodoAcademia,
)


@admin.register(Indicador)
class IndicadorAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'area', 'nome', 'premiacao', 'proporcao', 'ordem', 'ativo')
    list_filter = ('area', 'ativo', 'empresa')
    search_fields = ('nome',)
    ordering = ('empresa', 'area', 'ordem', 'nome')


class ItemPeriodoAcademiaInline(admin.TabularInline):
    model = ItemPeriodoAcademia
    extra = 0


@admin.register(PeriodoAcademia)
class PeriodoAcademiaAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'ano', 'mes', 'data_referencia', 'qt_ativos', 'qt_cancelados', 'churn_pct')
    list_filter = ('ano', 'mes', 'empresa')
    inlines = [ItemPeriodoAcademiaInline]


class ItemAtendenteDiarioInline(admin.TabularInline):
    model = ItemAtendenteDiario
    extra = 0


@admin.register(LancamentoVendasDiario)
class LancamentoVendasDiarioAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'empresa', 'data', 'oport_balcao', 'balcao', 'site', 'total_dia',
        'total_cancel_dia', 'saldo_comercial', 'churn_dia',
    )
    list_filter = ('empresa',)
    ordering = ('-data',)
    inlines = [ItemAtendenteDiarioInline]


@admin.register(AtendenteAcademia)
class AtendenteAcademiaAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'nome', 'ordem', 'ativo')
    list_filter = ('empresa', 'ativo')
    ordering = ('empresa', 'ordem', 'nome')
