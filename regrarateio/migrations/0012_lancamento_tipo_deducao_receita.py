from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0011_lancamento_origem_total_convenio'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lancamentorateio',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('PGTO', 'Pagamento'),
                    ('RECEBIMENTO', 'Recebimento'),
                    ('DEDUCAO_RECEITA', 'DEDUCAO DA RECEITA'),
                ],
                max_length=20,
                verbose_name='Tipo',
            ),
        ),
    ]
