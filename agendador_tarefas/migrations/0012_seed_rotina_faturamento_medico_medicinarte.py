from datetime import date

from django.db import migrations


def seed_faturamento_medico_medicinarte(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')
    from agendador_tarefas.seed_rotina_medicinarte import criar_rotina_faturamento_medico_medicinarte

    criar_rotina_faturamento_medico_medicinarte(
        TarefaAgendada,
        Empresa,
        inicio=date(2026, 8, 1),
        fim=date(2026, 8, 31),
    )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')
    from agendador_tarefas.seed_rotina_medicinarte import (
        NOME_FANTASIA,
        ROTINA_FATURAMENTO_MEDICO,
        empresa_por_nome_fantasia,
    )

    empresa = empresa_por_nome_fantasia(Empresa, NOME_FANTASIA)
    if not empresa:
        return
    titulos = [r['titulo'] for r in ROTINA_FATURAMENTO_MEDICO]
    TarefaAgendada.objects.filter(
        empresa=empresa,
        titulo__in=titulos,
        data__gte=date(2026, 8, 1),
        data__lte=date(2026, 8, 31),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0011_seed_rotina_diaria_agosto2026'),
    ]

    operations = [
        migrations.RunPython(seed_faturamento_medico_medicinarte, reverter),
    ]
