from django.db import migrations


def restringir_agenda_medicinarte(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')

    from agendador_tarefas.seed_faturamento import (
        empresa_agenda_faturamento,
        queryset_tarefas_seed_agenda,
    )

    medicinarte = empresa_agenda_faturamento(Empresa)
    if not medicinarte:
        return

    queryset_tarefas_seed_agenda(TarefaAgendada).exclude(
        empresa=medicinarte,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0007_tarefaresponsavellog'),
    ]

    operations = [
        migrations.RunPython(restringir_agenda_medicinarte, migrations.RunPython.noop),
    ]
