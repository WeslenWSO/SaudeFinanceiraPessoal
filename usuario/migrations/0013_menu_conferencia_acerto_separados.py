from django.db import migrations


def espelhar_permissoes_conferencia_acerto(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    usuarios_acerto = set(
        PermissaoMenuUsuario.objects.filter(codigo='faturamento_acerto_caixa').values_list(
            'usuario_id', flat=True
        )
    )
    usuarios_conf = set(
        PermissaoMenuUsuario.objects.filter(codigo='faturamento_conferencia').values_list(
            'usuario_id', flat=True
        )
    )
    novos = []
    for uid in usuarios_acerto - usuarios_conf:
        novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo='faturamento_conferencia'))
    for uid in usuarios_conf - usuarios_acerto:
        novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo='faturamento_acerto_caixa'))
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0012_menu_acerto_caixa'),
    ]

    operations = [
        migrations.RunPython(espelhar_permissoes_conferencia_acerto, migrations.RunPython.noop),
    ]
