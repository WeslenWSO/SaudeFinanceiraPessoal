from django.db import migrations


def copiar_permissao_faturamento_para_acerto_caixa(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    usuarios = PermissaoMenuUsuario.objects.filter(
        codigo='faturamento_medico',
    ).values_list('usuario_id', flat=True)
    novos = [
        PermissaoMenuUsuario(usuario_id=uid, codigo='faturamento_acerto_caixa')
        for uid in set(usuarios)
    ]
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0011_menu_estoque_imobilizado'),
    ]

    operations = [
        migrations.RunPython(
            copiar_permissao_faturamento_para_acerto_caixa,
            migrations.RunPython.noop,
        ),
    ]
