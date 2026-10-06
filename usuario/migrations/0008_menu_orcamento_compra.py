from django.db import migrations


def copiar_permissao_contas_pagar(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    usuarios = PermissaoMenuUsuario.objects.filter(codigo='contas_pagar').values_list('usuario_id', flat=True)
    novos = [
        PermissaoMenuUsuario(usuario_id=uid, codigo='orcamento_compra')
        for uid in set(usuarios)
    ]
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0007_resumo_fechamento_resultado_menu'),
    ]

    operations = [
        migrations.RunPython(copiar_permissao_contas_pagar, migrations.RunPython.noop),
    ]
