from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0009_seed_agenda_anestesia'),
    ]

    operations = [
        migrations.AddField(
            model_name='tarefaagendada',
            name='hora_fim',
            field=models.TimeField(blank=True, null=True, verbose_name='Hora fim'),
        ),
        migrations.AddField(
            model_name='tarefaagendada',
            name='hora_inicio',
            field=models.TimeField(blank=True, null=True, verbose_name='Hora início'),
        ),
        migrations.AlterField(
            model_name='tarefaagendada',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='tarefas_agendadas',
                to='empresa.empresa',
                verbose_name='Empresa',
            ),
        ),
    ]
