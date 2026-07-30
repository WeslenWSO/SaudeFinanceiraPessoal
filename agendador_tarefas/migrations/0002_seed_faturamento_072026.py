from datetime import date

from django.db import migrations


def criar_tarefas_faturamento_072026(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')

    from agendador_tarefas.seed_faturamento import tarefas_faturamento_competencia

    dados = tarefas_faturamento_competencia(
        competencia_mes=7,
        competencia_ano=2026,
        inicio_mes=8,
        inicio_ano=2026,
    )
    data_inicio = date(2026, 8, 1)

    for empresa in Empresa.objects.filter(status='Ativa'):
        for item in dados:
            TarefaAgendada.objects.get_or_create(
                empresa=empresa,
                competencia_mes=7,
                competencia_ano=2026,
                titulo=item['titulo'],
                defaults={
                    'data': data_inicio,
                    'previsao_conclusao': item['previsao_conclusao'],
                    'descricao': item['descricao'],
                    'status': 'pendente',
                    'responsavel': '',
                },
            )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    TarefaAgendada.objects.filter(
        competencia_mes=7,
        competencia_ano=2026,
        titulo__in=[
            'Postal Saúde', 'Bombeiro', 'Polícia Militar', 'Fusex', 'Profarma',
            'PPSaude', 'Bradesco', 'Geap', 'Cassi',
        ],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_tarefas_faturamento_072026, reverter),
    ]
