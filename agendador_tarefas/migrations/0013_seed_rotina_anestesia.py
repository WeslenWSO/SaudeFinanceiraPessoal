from datetime import date

from django.db import migrations


def seed_rotina_anestesia(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')
    from agendador_tarefas.seed_rotina_anestesia import criar_rotina_anestesia

    criar_rotina_anestesia(
        TarefaAgendada,
        Empresa,
        inicio=date(2026, 8, 1),
        fim=date(2026, 8, 31),
        repasse_meses=12,
    )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')
    from agendador_tarefas.seed_rotina_anestesia import (
        NOME_FANTASIA,
        ROTINA_FATURAMENTO_MEDICO,
        TITULO_FECHAMENTO_REPASSE,
        empresa_por_nome_fantasia,
    )

    empresa = empresa_por_nome_fantasia(Empresa, NOME_FANTASIA)
    if not empresa:
        return
    titulos = [r['titulo'] for r in ROTINA_FATURAMENTO_MEDICO] + [TITULO_FECHAMENTO_REPASSE]
    TarefaAgendada.objects.filter(empresa=empresa, titulo__in=titulos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0012_seed_rotina_faturamento_medico_medicinarte'),
    ]

    operations = [
        migrations.RunPython(seed_rotina_anestesia, reverter),
    ]
