from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0052_itemservico_valor_pago'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='valor_acrescimo',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Acréscimo informado no RIS (coluna Acréscimo/Desconto quando positivo).',
                max_digits=10,
                verbose_name='Acréscimo',
            ),
        ),
    ]
