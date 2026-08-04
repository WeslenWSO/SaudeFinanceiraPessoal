from django.contrib import admin
from .models import Convenio, ServicosMedicos, TabelaPreco

@admin.register(Convenio)
class ConvenioAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome', 'empresa', 'dia_fechamento', 'dia_abertura', 'observacao_resumo')
    list_display_links = ('id', 'nome')
    list_per_page = 10
    search_fields = ('nome',)

    @admin.display(description='Observação')
    def observacao_resumo(self, obj):
        texto = (obj.observacao or '').strip()
        if not texto:
            return '—'
        return texto[:80] + ('…' if len(texto) > 80 else '')

@admin.register(ServicosMedicos)
class ServicosMedicosAdmin(admin.ModelAdmin):
    list_display = ('id', 'codigo', 'servicos', 'porte_anestesico')
    list_display_links = ('id', 'codigo')
    list_per_page = 10
    search_fields = ('codigo', 'servicos')

@admin.register(TabelaPreco)
class TabelaPrecoAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'convenio', 'codigo_servico', 'preco_apartamento', 'preco_enfermaria')
    list_display_links = ('id', 'empresa')
    list_per_page = 10
    search_fields = ('empresa__razao', 'convenio__nome', 'codigo_servico__codigo')
