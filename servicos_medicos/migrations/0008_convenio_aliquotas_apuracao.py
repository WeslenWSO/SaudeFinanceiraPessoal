from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servicos_medicos', '0007_convenio_observacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='convenio',
            name='aliquota_iss_ap',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='ISS apuração (%)',
            ),
        ),
        migrations.AddField(
            model_name='convenio',
            name='aliquota_pis_ap',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='PIS apuração (%)',
            ),
        ),
        migrations.AddField(
            model_name='convenio',
            name='aliquota_cofins_ap',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='COFINS apuração (%)',
            ),
        ),
        migrations.AddField(
            model_name='convenio',
            name='aliquota_csll_ap',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='CSLL apuração (%)',
            ),
        ),
        migrations.AddField(
            model_name='convenio',
            name='aliquota_irpj_ap',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name='IRPJ apuração (%)',
            ),
        ),
    ]
