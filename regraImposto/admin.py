from django.contrib import admin
from .models import RegraImposto

# Register your models here.
class RegraImpostoAdmin(admin.ModelAdmin):
    list_display = ('id','DescricaoRegraImposto' ,"aliquota_pis","aliquota_cofins","aliquota_csll","aliquota_irpj","aliquota_iss_apuracao","percentual_calculo")
    list_display_links = ('id', 'DescricaoRegraImposto',"aliquota_iss_apuracao")


    list_per_page = 10
    
admin.site.register(RegraImposto, RegraImpostoAdmin)