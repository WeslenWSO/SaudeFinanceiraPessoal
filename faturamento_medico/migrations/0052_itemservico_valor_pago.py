from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0051_acerto_caixa_conta_bancaria'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='valor_pago',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Valor pago pelo paciente/convênio (coluna Valor pago do RIS).',
                max_digits=10,
                null=True,
                verbose_name='Valor pago',
            ),
        ),
    ]
