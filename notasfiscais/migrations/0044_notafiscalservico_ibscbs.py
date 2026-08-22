from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notasfiscais', '0043_notafiscalservico_motivo_cancelamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='notafiscalservico',
            name='aliquota_cbs',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=7, verbose_name='Alíquota CBS (%)'),
        ),
        migrations.AddField(
            model_name='notafiscalservico',
            name='aliquota_ibs',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=7, verbose_name='Alíquota IBS (%)'),
        ),
        migrations.AddField(
            model_name='notafiscalservico',
            name='base_ibs_cbs',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Base de cálculo IBS/CBS (reforma tributária), tag vBC do XML.',
                max_digits=15,
                verbose_name='Base IBS/CBS',
            ),
        ),
        migrations.AddField(
            model_name='notafiscalservico',
            name='valor_cbs',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Valor da CBS destacada no XML nacional (vCBS / vCBSTot).',
                max_digits=15,
                verbose_name='Valor CBS',
            ),
        ),
        migrations.AddField(
            model_name='notafiscalservico',
            name='valor_ibs',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Valor do IBS destacado no XML nacional (vIBS / vIBSTot).',
                max_digits=15,
                verbose_name='Valor IBS',
            ),
        ),
    ]
