from django.db import migrations, models


def limpar_protocolo_vazio(apps, schema_editor):
    FaturamentoMedico = apps.get_model('faturamento_medico', 'FaturamentoMedico')
    FaturamentoMedico.objects.filter(guia_lancada__in=['0', 'None', 'False']).update(guia_lancada='')


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0037_metamodalidadesolicitante_meta_unica'),
    ]

    operations = [
        migrations.AlterField(
            model_name='faturamentomedico',
            name='guia_lancada',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Protocolo'),
        ),
        migrations.RunPython(limpar_protocolo_vazio, migrations.RunPython.noop),
    ]
