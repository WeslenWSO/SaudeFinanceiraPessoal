from django.db import migrations


def copiar_permissao_analise_compra(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    ja = set(
        PermissaoMenuUsuario.objects.filter(codigo='estoque_analise_compra').values_list(
            'usuario_id', flat=True
        )
    )
    novos = []
    for uid in PermissaoMenuUsuario.objects.filter(codigo='estoque_farmacia').values_list(
        'usuario_id', flat=True
    ):
        if uid not in ja:
            novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo='estoque_analise_compra'))
            ja.add(uid)
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0015_menu_estoque_kpis'),
    ]

    operations = [
        migrations.RunPython(copiar_permissao_analise_compra, migrations.RunPython.noop),
    ]
