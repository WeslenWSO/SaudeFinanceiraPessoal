from datetime import date

from django.db import migrations


def seed_rotina_agosto_2026(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    from agendador_tarefas.seed_rotina_diaria import criar_rotina_diaria_geral

    criar_rotina_diaria_geral(
        TarefaAgendada,
        inicio=date(2026, 8, 1),
        fim=date(2026, 8, 31),
    )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    from agendador_tarefas.seed_rotina_diaria import ROTINAS_DIARIAS

    titulos = [r['titulo'] for r in ROTINAS_DIARIAS]
    TarefaAgendada.objects.filter(
        empresa__isnull=True,
        titulo__in=titulos,
        data__gte=date(2026, 8, 1),
        data__lte=date(2026, 8, 31),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0010_tarefa_geral_horarios'),
    ]

    operations = [
        migrations.RunPython(seed_rotina_agosto_2026, reverter),
    ]
