from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emprestimos', '0006_emprestimo_custos_saldo'),
    ]

    operations = [
        migrations.AddField(
            model_name='parcelaemprestimo',
            name='multa',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=15,
                verbose_name='Multa (atraso)',
            ),
        ),
    ]
