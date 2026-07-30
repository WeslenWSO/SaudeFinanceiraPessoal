from django.db import migrations


def seed_agenda_anestesia(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')

    from agendador_tarefas.seed_faturamento import (
        CONVENIOS_ANESTESIA,
        criar_tarefas_empresa,
        empresa_por_nome_fantasia,
    )

    empresa = empresa_por_nome_fantasia(Empresa, 'SECURITY HEALTH ANESTESIA')
    if not empresa:
        return

    criar_tarefas_empresa(
        TarefaAgendada,
        empresa,
        convenios=CONVENIOS_ANESTESIA,
        competencia_mes=7,
        competencia_ano=2026,
        inicio_mes=8,
        inicio_ano=2026,
    )


def reverter(apps, schema_editor):
    TarefaAgendada = apps.get_model('agendador_tarefas', 'TarefaAgendada')
    Empresa = apps.get_model('empresa', 'Empresa')

    from agendador_tarefas.seed_faturamento import (
        CONVENIOS_ANESTESIA,
        empresa_por_nome_fantasia,
        queryset_tarefas_seed_agenda,
    )

    empresa = empresa_por_nome_fantasia(Empresa, 'SECURITY HEALTH ANESTESIA')
    if not empresa:
        return

    titulos_glosa = {f'{c} — Recurso de Glosa' for c in CONVENIOS_ANESTESIA}
    queryset_tarefas_seed_agenda(TarefaAgendada).filter(
        empresa=empresa,
        titulo__in=set(CONVENIOS_ANESTESIA) | titulos_glosa,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agendador_tarefas', '0008_agenda_apenas_medicinarte'),
    ]

    operations = [
        migrations.RunPython(seed_agenda_anestesia, reverter),
    ]
