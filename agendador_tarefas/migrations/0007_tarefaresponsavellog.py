import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('agendador_tarefas', '0006_tarefaagendada_criado_por'),
    ]

    operations = [
        migrations.CreateModel(
            name='TarefaResponsavelLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('responsavel_anterior', models.CharField(blank=True, default='', max_length=120, verbose_name='Responsável anterior')),
                ('responsavel_novo', models.CharField(blank=True, default='', max_length=120, verbose_name='Responsável novo')),
                ('alterado_em', models.DateTimeField(auto_now_add=True, verbose_name='Quando')),
                ('observacao', models.TextField(blank=True, default='', verbose_name='Observação')),
                ('alterado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='logs_passagem_tarefa', to=settings.AUTH_USER_MODEL, verbose_name='Quem passou')),
                ('tarefa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs_responsavel', to='agendador_tarefas.tarefaagendada', verbose_name='Tarefa')),
            ],
            options={
                'verbose_name': 'Log de responsável',
                'verbose_name_plural': 'Logs de responsável',
                'ordering': ['-alterado_em'],
            },
        ),
    ]
