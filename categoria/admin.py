from django.contrib import admin

from categoria.models import Categoria

# Register your models here.
class CategoriaAdmin(admin.ModelAdmin):

    list_display = ('id','nome', 'classificacao','sintetico')
    list_display_links = ('id', 'nome','classificacao','sintetico')

    list_per_page = 10

admin.site.register(Categoria, CategoriaAdmin)