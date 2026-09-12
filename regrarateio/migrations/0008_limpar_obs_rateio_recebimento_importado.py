from django.db import migrations


def limpar_obs_recebimento_importado(apps, schema_editor):
    LancamentoRateio = apps.get_model('regrarateio', 'LancamentoRateio')
    LancamentoRateio.objects.filter(
        tipo='RECEBIMENTO',
        origem='IMPORTACAO',
    ).exclude(obs='').update(obs='')


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0007_lancamentorateio_campos_importacao'),
    ]

    operations = [
        migrations.RunPython(limpar_obs_recebimento_importado, migrations.RunPython.noop),
    ]
