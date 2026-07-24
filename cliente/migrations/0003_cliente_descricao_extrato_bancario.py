# Generated manually for Cliente.descricao_extrato_bancario

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cliente', '0002_cliente_empresa'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='descricao_extrato_bancario',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Trecho que aparece no histórico do extrato para este CNPJ/CPF. Conciliação automática quando CNPJ no extrato e nome curto não batem.',
                max_length=255,
                verbose_name='Texto no extrato bancário',
            ),
        ),
    ]
