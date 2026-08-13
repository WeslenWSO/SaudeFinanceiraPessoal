from django.db import migrations


def consolidar_metas_unicas(apps, schema_editor):
    Meta = apps.get_model('faturamento_medico', 'MetaModalidadeSolicitante')
    melhor = {}
    for row in Meta.objects.all().order_by('empresa_id', 'solicitante', 'modalidade', '-meta'):
        chave = (row.empresa_id, row.solicitante, row.modalidade)
        if chave not in melhor:
            melhor[chave] = row.id
        else:
            Meta.objects.filter(id=row.id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0036_metamodalidadesolicitante_mes'),
    ]

    operations = [
        migrations.RunPython(consolidar_metas_unicas, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='metamodalidadesolicitante',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='metamodalidadesolicitante',
            name='ano',
        ),
        migrations.RemoveField(
            model_name='metamodalidadesolicitante',
            name='mes',
        ),
        migrations.AlterUniqueTogether(
            name='metamodalidadesolicitante',
            unique_together={('empresa', 'solicitante', 'modalidade')},
        ),
    ]
