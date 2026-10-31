from datetime import date, timedelta

from django.db import migrations


def seed_backup_drive(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    from agendador_tarefas.seed_backup_banco import criar_tarefas_backup_banco_agenda

    hoje = date.today()
    criar_tarefas_backup_banco_agenda(
        TarefaAgendada,
        inicio=hoje,
        fim=hoje + timedelta(days=365),
    )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    from agendador_tarefas.seed_backup_banco import TITULO_BACKUP_BANCO

    TarefaAgendada.objects.filter(empresa_id__isnull=True, titulo=TITULO_BACKUP_BANCO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0015_tarefa_tramite'),
    ]

    operations = [
        migrations.RunPython(seed_backup_drive, reverter),
    ]
