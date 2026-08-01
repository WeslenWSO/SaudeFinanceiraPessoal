from django.db import migrations


def conceder_dashboard_a_usuarios_conta_azul(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    com_ca = set(
        PermissaoMenuUsuario.objects.filter(codigo='conta_azul').values_list('usuario_id', flat=True)
    )
    com_dash = set(
        PermissaoMenuUsuario.objects.filter(codigo='dashboard').values_list('usuario_id', flat=True)
    )
    novos = [
        PermissaoMenuUsuario(usuario_id=uid, codigo='dashboard')
        for uid in com_ca - com_dash
    ]
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0005_menu_conta_azul_erp'),
    ]

    operations = [
        migrations.RunPython(conceder_dashboard_a_usuarios_conta_azul, migrations.RunPython.noop),
    ]
