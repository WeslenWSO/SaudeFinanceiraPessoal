from django.db import migrations


def copiar_permissoes_estoque_imobilizado(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    novos = []
    for uid in PermissaoMenuUsuario.objects.filter(codigo='estoque_farmacia').values_list(
        'usuario_id', flat=True
    ):
        novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo='estoque_imobilizado'))
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('usuario', '0010_inventario_menu_fiscal'),
    ]

    operations = [
        migrations.RunPython(copiar_permissoes_estoque_imobilizado, migrations.RunPython.noop),
    ]
