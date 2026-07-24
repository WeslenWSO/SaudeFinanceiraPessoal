from django.contrib import admin

from OPCARTAO.models import Opcartao


# Register your models here.
class OpCartaoAdmin(admin.ModelAdmin):

    list_display = ('id','descricao','tband')
    list_display_links = ('id', 'descricao','tband')

    list_per_page = 10

admin.site.register(Opcartao , OpCartaoAdmin)