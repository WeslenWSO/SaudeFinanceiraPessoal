# Generated manually to fix observacoes field null constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notasfiscais', '0033_rename_data_log_to_data_segmentacao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lognotafiscal',
            name='observacoes',
            field=models.TextField(blank=True, null=True, verbose_name='Observações'),
        ),
    ]