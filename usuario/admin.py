from django.contrib import admin
from .models import Usuario

# Register your models here.
class UsuarioAdmin(admin.ModelAdmin):

    list_display = ('id','usuario','lastname')
    list_display_links = ('id', 'usuario','lastname')

    list_per_page = 10

admin.site.register(Usuario, UsuarioAdmin)