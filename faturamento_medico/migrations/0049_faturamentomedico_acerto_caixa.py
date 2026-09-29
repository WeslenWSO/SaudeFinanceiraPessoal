from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0048_itemservico_valor_desconto'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='marcado_acerto_caixa',
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name='Marcado para acerto de caixa',
            ),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='caixa_acerto',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Beatriz', 'Caixa - Beatriz'),
                    ('Estela', 'Caixa - Estela'),
                    ('Vitoria', 'Caixa - Vitoria'),
                    ('Joao', 'Caixa - João'),
                    ('Marcela', 'Caixa - Marcela'),
                    ('Laura', 'Caixa - Laura'),
                    ('Thaine', 'Caixa - Thaine'),
                ],
                default='',
                max_length=40,
                verbose_name='Caixa (acerto)',
            ),
        ),
    ]
