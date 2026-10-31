from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='backupexecucaoagendada',
            name='arquivo_nome',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='backupexecucaoagendada',
            name='drive_file_id',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='backupexecucaoagendada',
            name='mensagem',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='backupexecucaoagendada',
            name='origem',
            field=models.CharField(
                blank=True,
                default='cron',
                help_text='cron, manual ou forcar',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='backupexecucaoagendada',
            name='sucesso',
            field=models.BooleanField(default=False),
        ),
    ]
