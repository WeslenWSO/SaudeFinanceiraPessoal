from django.conf import settings
from django.db import migrations


def conceder_conta_azul_erp(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    usuarios_com_conta_azul = set(
        PermissaoMenuUsuario.objects.filter(codigo='conta_azul').values_list('usuario_id', flat=True)
    )
    batch = [
        PermissaoMenuUsuario(usuario_id=uid, codigo='conta_azul_erp')
        for uid in usuarios_com_conta_azul
    ]
    if batch:
        PermissaoMenuUsuario.objects.bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('usuario', '0004_permissao_menu'),
    ]

    operations = [
        migrations.RunPython(conceder_conta_azul_erp, migrations.RunPython.noop),
    ]
