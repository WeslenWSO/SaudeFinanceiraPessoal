from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notasfiscais', '0042_alter_notafiscalservico_numero_dps'),
    ]

    operations = [
        migrations.AddField(
            model_name='notafiscalservico',
            name='codigo_motivo_cancelamento',
            field=models.CharField(
                blank=True,
                default='',
                max_length=10,
                verbose_name='Código motivo cancelamento',
            ),
        ),
        migrations.AddField(
            model_name='notafiscalservico',
            name='motivo_cancelamento',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Motivo do cancelamento',
            ),
        ),
    ]
