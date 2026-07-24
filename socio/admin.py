from django.contrib import admin
from .models import Socio

# Register your models here.
class SociosAdmin(admin.ModelAdmin):

    list_display = ('id','socio','lastname')
    list_display_links = ('id', 'socio','lastname')

    list_per_page = 10

admin.site.register(Socio, SociosAdmin)