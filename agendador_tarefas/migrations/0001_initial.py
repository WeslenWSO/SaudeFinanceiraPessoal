from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('empresa', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TarefaAgendada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('competencia_mes', models.PositiveSmallIntegerField(db_index=True, verbose_name='Competência (mês)')),
                ('competencia_ano', models.PositiveSmallIntegerField(db_index=True, verbose_name='Competência (ano)')),
                ('data', models.DateField(db_index=True, verbose_name='Data')),
                ('previsao_conclusao', models.DateField(verbose_name='Previsão de conclusão')),
                ('status', models.CharField(choices=[('pendente', 'Pendente'), ('concluido', 'Concluído'), ('com_supervisor', 'Com Supervisor')], db_index=True, default='pendente', max_length=20, verbose_name='Status')),
                ('responsavel', models.CharField(blank=True, default='', max_length=120, verbose_name='Responsável')),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('descricao', models.TextField(blank=True, default='', verbose_name='Descrição')),
                ('data_conclusao', models.DateField(blank=True, null=True, verbose_name='Data da conclusão')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('concluido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tarefas_concluidas', to=settings.AUTH_USER_MODEL, verbose_name='Quem concluiu')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tarefas_agendadas', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Tarefa agendada',
                'verbose_name_plural': 'Tarefas agendadas',
                'ordering': ['previsao_conclusao', 'titulo'],
                'indexes': [models.Index(fields=['empresa', 'competencia_ano', 'competencia_mes'], name='agendador_t_empresa_7a0f0d_idx')],
            },
        ),
    ]
