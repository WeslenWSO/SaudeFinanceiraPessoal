from django.db import migrations


def copiar_permissoes_nf_entrada(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    usuarios = PermissaoMenuUsuario.objects.filter(codigo='nf_entrada').values_list('usuario_id', flat=True)
    novos = []
    for codigo in ('estoque_farmacia', 'estoque_requisicoes', 'estoque_relatorio'):
        for uid in usuarios:
            novos.append(PermissaoMenuUsuario(usuario_id=uid, codigo=codigo))
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('usuario', '0008_menu_orcamento_compra'),
    ]

    operations = [
        migrations.RunPython(copiar_permissoes_nf_entrada, migrations.RunPython.noop),
    ]
