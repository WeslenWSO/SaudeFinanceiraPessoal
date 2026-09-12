from django.db import migrations


def conceder_resumo_resultado_a_quem_tem_fechamento(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    com_fechamento = set(
        PermissaoMenuUsuario.objects.filter(codigo='resumo_fechamento').values_list(
            'usuario_id', flat=True
        )
    )
    com_novo = set(
        PermissaoMenuUsuario.objects.filter(codigo='resumo_fechamento_resultado').values_list(
            'usuario_id', flat=True
        )
    )
    novos = [
        PermissaoMenuUsuario(usuario_id=uid, codigo='resumo_fechamento_resultado')
        for uid in com_fechamento - com_novo
    ]
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0006_dashboard_conta_azul_menu'),
    ]

    operations = [
        migrations.RunPython(
            conceder_resumo_resultado_a_quem_tem_fechamento,
            migrations.RunPython.noop,
        ),
    ]
