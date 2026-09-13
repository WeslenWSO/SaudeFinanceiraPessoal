from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0010_cobranca_convenios_a_faturar'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lancamentorateio',
            name='origem',
            field=models.CharField(
                blank=True,
                choices=[
                    ('PAGAR', 'Pagar'),
                    ('RECEBER', 'Receber'),
                    ('IMPORTACAO', 'IMPORTACAO'),
                    ('TOTAL CONVENIO', 'TOTAL CONVENIO'),
                ],
                default='',
                max_length=20,
                verbose_name='Origem',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='lancamentorateio',
            name='lancamento_rateio_cap_ou_car',
        ),
        migrations.AddConstraint(
            model_name='lancamentorateio',
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(('conta_pagar__isnull', False), ('conta_receber__isnull', True)),
                    models.Q(('conta_pagar__isnull', True), ('conta_receber__isnull', False)),
                    models.Q(
                        ('conta_pagar__isnull', True),
                        ('conta_receber__isnull', True),
                        ('origem', 'TOTAL CONVENIO'),
                    ),
                    _connector='OR',
                ),
                name='lancamento_rateio_cap_ou_car',
            ),
        ),
    ]
