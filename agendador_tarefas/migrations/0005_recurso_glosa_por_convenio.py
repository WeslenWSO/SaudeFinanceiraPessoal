from django.db import migrations


def criar_glosa_por_convenio(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')

    from agendador_tarefas.seed_faturamento import tarefas_recurso_glosa_mensal

    TarefaAgendada.objects.filter(titulo='Verificar glosa').delete()

    itens = tarefas_recurso_glosa_mensal(
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
    TarefaAgendada.objects.filter(titulo__endswith='— Recurso de Glosa').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0004_rename_agendador_t_empresa_7a0f0d_idx_agendador_t_empresa_96cf94_idx'),
    ]

    operations = [
        migrations.RunPython(criar_glosa_por_convenio, reverter),
    ]
