from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emprestimos', '0004_simulacao_quitacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='simulacaoquitacaoemprestimo',
            name='total_parcela_original',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Soma do valor de face das parcelas selecionadas (antes da quitação).',
                max_digits=15,
                verbose_name='Soma parcelas originais',
            ),
        ),
    ]
