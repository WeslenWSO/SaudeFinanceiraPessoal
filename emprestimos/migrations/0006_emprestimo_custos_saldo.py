from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emprestimos', '0005_simulacao_total_parcela_original'),
    ]

    operations = [
        migrations.AddField(
            model_name='emprestimo',
            name='valor_tributos',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Tributos',
            ),
        ),
        migrations.AddField(
            model_name='emprestimo',
            name='valor_tarifas',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Tarifas',
            ),
        ),
        migrations.AddField(
            model_name='emprestimo',
            name='valor_registros',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Registros',
            ),
        ),
        migrations.AddField(
            model_name='emprestimo',
            name='valor_servicos_terceiros',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=15,
                verbose_name='Pagtos. servs. terceiros',
            ),
        ),
        migrations.AddField(
            model_name='emprestimo',
            name='saldo_devedor_atualizado',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Saldo do PDF na data de emissão do extrato.',
                max_digits=15,
                verbose_name='Saldo devedor atualizado',
            ),
        ),
    ]
