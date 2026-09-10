from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0047_extratopagamentoconvenio_status_recebimento'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='valor_desconto',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                verbose_name='Valor do Desconto',
            ),
        ),
    ]
