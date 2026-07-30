import calendar
from datetime import date

from django.db import migrations


def corrigir_fechamento_repasse_anestesia(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')
    from agendador_tarefas.seed_rotina_anestesia import (
        NOME_FANTASIA,
        TITULO_FECHAMENTO_REPASSE,
        empresa_por_nome_fantasia,
    )

    empresa = empresa_por_nome_fantasia(Empresa, NOME_FANTASIA)
    if not empresa:
        return

    for tarefa in TarefaAgendada.objects.filter(
        empresa=empresa,
        titulo=TITULO_FECHAMENTO_REPASSE,
    ):
        mes = tarefa.competencia_mes
        ano = tarefa.competencia_ano
        ultimo = calendar.monthrange(ano, mes)[1]
        tarefa.data = date(ano, mes, 15)
        tarefa.previsao_conclusao = date(ano, mes, min(20, ultimo))
        tarefa.descricao = (
            f'Fechamento do repasse — do dia 15 ao 20 de cada mês. '
            f'Competência {mes:02d}/{ano}.'
        )
        tarefa.save(update_fields=['data', 'previsao_conclusao', 'descricao'])


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0013_seed_rotina_anestesia'),
    ]

    operations = [
        migrations.RunPython(corrigir_fechamento_repasse_anestesia, migrations.RunPython.noop),
    ]
