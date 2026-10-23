from django.db import migrations


def copiar_inventario_para_quem_tem_estoque_fiscal(apps, schema_editor):
    """Quem já tinha inventário no Cadastro mantém; quem tem estoque fiscal ganha inventário."""
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    ja_tem = set(
        PermissaoMenuUsuario.objects.filter(codigo='inventario').values_list('usuario_id', flat=True)
    )
    novos = []
    for uid in PermissaoMenuUsuario.objects.filter(codigo='estoque_farmacia').values_list(
        'usuario_id', flat=True
    ):
        if uid not in ja_tem:
            novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo='inventario'))
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('usuario', '0009_menu_estoque_fiscal'),
    ]

    operations = [
        migrations.RunPython(copiar_inventario_para_quem_tem_estoque_fiscal, migrations.RunPython.noop),
    ]
