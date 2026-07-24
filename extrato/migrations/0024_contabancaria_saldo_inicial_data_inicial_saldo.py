from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0023_fix_baixacontaareceber_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='contabancaria',
            name='data_inicial_saldo',
            field=models.DateField(blank=True, null=True, verbose_name='Data Inicial do Saldo'),
        ),
        migrations.AddField(
            model_name='contabancaria',
            name='saldo_inicial',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14, verbose_name='Valor de Saldo Inicial'),
        ),
    ]
