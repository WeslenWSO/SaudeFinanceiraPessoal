from django.db import migrations


def garantir_permissao_acerto_caixa(apps, schema_editor):
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    codigos_origem = ('faturamento_conferencia', 'faturamento_medico', 'faturamento_acerto_caixa')
    usuarios = set()
    for cod in codigos_origem:
        usuarios.update(
            PermissaoMenuUsuario.objects.filter(codigo=cod).values_list('usuario_id', flat=True)
        )
    ja_tem = set(
        PermissaoMenuUsuario.objects.filter(codigo='faturamento_acerto_caixa').values_list(
            'usuario_id', flat=True
        )
    )
    novos = [
        PermissaoMenuUsuario(usuario_id=uid, codigo='faturamento_acerto_caixa')
        for uid in usuarios
        if uid not in ja_tem
    ]
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usuario', '0013_menu_conferencia_acerto_separados'),
    ]

    operations = [
        migrations.RunPython(garantir_permissao_acerto_caixa, migrations.RunPython.noop),
    ]
