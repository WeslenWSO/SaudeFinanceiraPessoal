from django.contrib import admin

from .models import TarefaAgendada, TarefaResponsavelLog, TarefaTramite


class TarefaResponsavelLogInline(admin.TabularInline):
    model = TarefaResponsavelLog
    extra = 0
    readonly_fields = ('responsavel_anterior', 'responsavel_novo', 'alterado_por', 'alterado_em', 'observacao')
    can_delete = False


class TarefaTramiteInline(admin.TabularInline):
    model = TarefaTramite
    extra = 0
    readonly_fields = ('autor', 'criado_em')
    fields = ('texto', 'autor', 'criado_em')


@admin.register(TarefaAgendada)
class TarefaAgendadaAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'competencia_mes', 'competencia_ano', 'data',
        'previsao_conclusao', 'status', 'responsavel', 'criado_por', 'empresa',
    )
    list_filter = ('status', 'competencia_ano', 'competencia_mes', 'empresa')
    search_fields = ('titulo', 'descricao', 'responsavel')
    date_hierarchy = 'previsao_conclusao'
    inlines = [TarefaResponsavelLogInline, TarefaTramiteInline]


@admin.register(TarefaResponsavelLog)
class TarefaResponsavelLogAdmin(admin.ModelAdmin):
    list_display = (
        'tarefa', 'responsavel_anterior', 'responsavel_novo',
        'alterado_por', 'alterado_em',
    )
    list_filter = ('alterado_em',)
    search_fields = ('tarefa__titulo', 'responsavel_anterior', 'responsavel_novo')
    readonly_fields = ('tarefa', 'responsavel_anterior', 'responsavel_novo', 'alterado_por', 'alterado_em')


@admin.register(TarefaTramite)
class TarefaTramiteAdmin(admin.ModelAdmin):
    list_display = ('tarefa', 'autor', 'criado_em', 'texto')
    list_filter = ('criado_em',)
    search_fields = ('tarefa__titulo', 'texto', 'autor__username', 'autor__first_name')
    readonly_fields = ('tarefa', 'autor', 'criado_em')
    date_hierarchy = 'criado_em'
