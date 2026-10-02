from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0050_acertocaixafechamento'),
    ]

    operations = [
        migrations.AlterField(
            model_name='faturamentomedico',
            name='caixa_acerto',
            field=models.CharField(
                blank=True,
                default='',
                help_text='ID da conta bancária tipo Caixa (cadastro em Contas Bancárias).',
                max_length=40,
                verbose_name='Caixa (acerto)',
            ),
        ),
        migrations.AlterField(
            model_name='acertocaixafechamento',
            name='caixa',
            field=models.CharField(
                help_text='ID da conta bancária tipo Caixa.',
                max_length=40,
                verbose_name='Caixa',
            ),
        ),
    ]
