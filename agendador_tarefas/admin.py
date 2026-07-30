from django.contrib import admin

from .models import TarefaAgendada, TarefaResponsavelLog


class TarefaResponsavelLogInline(admin.TabularInline):
    model = TarefaResponsavelLog
    extra = 0
    readonly_fields = ('responsavel_anterior', 'responsavel_novo', 'alterado_por', 'alterado_em', 'observacao')
    can_delete = False


@admin.register(TarefaAgendada)
class TarefaAgendadaAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'competencia_mes', 'competencia_ano', 'data',
        'previsao_conclusao', 'status', 'responsavel', 'criado_por', 'empresa',
    )
    list_filter = ('status', 'competencia_ano', 'competencia_mes', 'empresa')
    search_fields = ('titulo', 'descricao', 'responsavel')
    date_hierarchy = 'previsao_conclusao'
    inlines = [TarefaResponsavelLogInline]


@admin.register(TarefaResponsavelLog)
class TarefaResponsavelLogAdmin(admin.ModelAdmin):
    list_display = (
        'tarefa', 'responsavel_anterior', 'responsavel_novo',
        'alterado_por', 'alterado_em',
    )
    list_filter = ('alterado_em',)
    search_fields = ('tarefa__titulo', 'responsavel_anterior', 'responsavel_novo')
    readonly_fields = ('tarefa', 'responsavel_anterior', 'responsavel_novo', 'alterado_por', 'alterado_em')
