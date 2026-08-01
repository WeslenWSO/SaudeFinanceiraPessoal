from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0027_contabancaria_conta_azul_unico'),
    ]

    operations = [
        migrations.AddField(
            model_name='contabancaria',
            name='saldo_conta_azul',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                verbose_name='Saldo Conta Azul',
            ),
        ),
        migrations.AddField(
            model_name='contabancaria',
            name='saldo_conta_azul_em',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Saldo Conta Azul atualizado em',
            ),
        ),
    ]
