from django.db import migrations


def copiar_permissao_kpis(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    ja = set(
        PermissaoMenuUsuario.objects.filter(codigo='estoque_kpis').values_list('usuario_id', flat=True)
    )
    novos = []
    for uid in PermissaoMenuUsuario.objects.filter(codigo='estoque_farmacia').values_list(
        'usuario_id', flat=True
    ):
        if uid not in ja:
            novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo='estoque_kpis'))
            ja.add(uid)
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0014_garantir_acerto_caixa_menu'),
    ]

    operations = [
        migrations.RunPython(copiar_permissao_kpis, migrations.RunPython.noop),
    ]
