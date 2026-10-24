from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0028_contabancaria_saldo_conta_azul'),
    ]

    operations = [
        migrations.AddField(
            model_name='contabancaria',
            name='inativo_acerto_caixa',
            field=models.BooleanField(
                default=False,
                help_text='Oculta esta conta no Acerto de Caixa. Permanece inativa aqui mesmo após sincronizar cadastros no Conta Azul.',
                verbose_name='Inativo no acerto de caixa',
            ),
        ),
    ]
