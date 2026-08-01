from django.contrib import admin

from categoria.models import Categoria, CentroCusto

# Register your models here.
class CategoriaAdmin(admin.ModelAdmin):

    list_display = ('id', 'nome', 'classificacao', 'tipo', 'conta_azul_id', 'bloquear_sync_conta_azul', 'sintetico')
    list_filter = ('tipo', 'bloquear_sync_conta_azul', 'sintetico')
    list_display_links = ('id', 'nome','classificacao','sintetico')

    list_per_page = 10

admin.site.register(Categoria, CategoriaAdmin)


@admin.register(CentroCusto)
class CentroCustoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'empresa', 'ativo', 'conta_azul_id')
    list_filter = ('empresa', 'ativo')
    search_fields = ('nome', 'conta_azul_id')