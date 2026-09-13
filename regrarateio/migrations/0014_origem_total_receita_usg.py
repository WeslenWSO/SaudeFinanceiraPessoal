from django.db import migrations, models


def renomear_origem(apps, schema_editor):
    LancamentoRateio = apps.get_model('regrarateio', 'LancamentoRateio')
    LancamentoRateio.objects.filter(origem='TOTAL CONVENIO').update(origem='Total Receita USG')


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0013_limpar_descricao_importacao_rateio'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='lancamentorateio',
            name='lancamento_rateio_cap_ou_car',
        ),
        migrations.RunPython(renomear_origem, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='lancamentorateio',
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(('conta_pagar__isnull', False), ('conta_receber__isnull', True)),
                    models.Q(('conta_pagar__isnull', True), ('conta_receber__isnull', False)),
                    models.Q(
                        ('conta_pagar__isnull', True),
                        ('conta_receber__isnull', True),
                        ('origem', 'Total Receita USG'),
                    ),
                    _connector='OR',
                ),
                name='lancamento_rateio_cap_ou_car',
            ),
        ),
        migrations.AlterField(
            model_name='lancamentorateio',
            name='origem',
            field=models.CharField(
                blank=True,
                choices=[
                    ('PAGAR', 'Pagar'),
                    ('RECEBER', 'Receber'),
                    ('IMPORTACAO', 'IMPORTACAO'),
                    ('Total Receita USG', 'Total Receita USG'),
                ],
                default='',
                max_length=20,
                verbose_name='Origem',
            ),
        ),
    ]
