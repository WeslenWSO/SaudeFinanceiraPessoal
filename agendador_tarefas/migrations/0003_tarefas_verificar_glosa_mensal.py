from django.db import migrations


def criar_tarefas_glosa_mensal(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')

    from agendador_tarefas.seed_faturamento import tarefas_verificar_glosa_mensal

    # A partir de ago/2026: glosa nos dias 01–10; competência = mês anterior
    itens = tarefas_verificar_glosa_mensal(
        execucao_mes=8,
        execucao_ano=2026,
        qtd_meses=12,
    )

    for empresa in Empresa.objects.filter(status='Ativa'):
        for item in itens:
            TarefaAgendada.objects.get_or_create(
                empresa=empresa,
                competencia_mes=item['competencia_mes'],
                competencia_ano=item['competencia_ano'],
                titulo=item['titulo'],
                defaults={
                    'data': item['data'],
                    'previsao_conclusao': item['previsao_conclusao'],
                    'descricao': item['descricao'],
                    'status': 'pendente',
                    'responsavel': '',
                },
            )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    TarefaAgendada.objects.filter(titulo='Verificar glosa').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0002_seed_faturamento_072026'),
    ]

    operations = [
        migrations.RunPython(criar_tarefas_glosa_mensal, reverter),
    ]
