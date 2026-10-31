from django.db import migrations


def resync_backup_tarefas(apps, schema_editor):
    BackupBancoConfig = apps.get_model('accounts', 'BackupBancoConfig')
    if not BackupBancoConfig.objects.exists():
        BackupBancoConfig.objects.create()

    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    from agendador_tarefas.seed_backup_banco import sincronizar_tarefas_backup_banco_agenda

    sincronizar_tarefas_backup_banco_agenda(TarefaAgendada)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('agendador_tarefas', '0016_seed_backup_postgres_drive'),
    ]

    operations = [
        migrations.RunPython(resync_backup_tarefas, migrations.RunPython.noop),
    ]
