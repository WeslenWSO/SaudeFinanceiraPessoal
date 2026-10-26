from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0053_itemservico_valor_acrescimo'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='pagamentos_acerto_json',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Rateio manual: lista {cobranca_id, valor}.',
                verbose_name='Pagamentos (acerto de caixa)',
            ),
        ),
    ]
