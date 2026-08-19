from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0042_apelidosolicitante'),
    ]

    operations = [
        migrations.AlterField(
            model_name='itemservico',
            name='status_conferencia',
            field=models.CharField(
                blank=True,
                choices=[
                    ('PENDENTE', 'PENDENTE'),
                    ('CONFERIDO', 'CONFERIDO'),
                    ('LOTE OK', 'LOTE OK'),
                    ('FALTA DE GUIA', 'FALTA DE GUIA'),
                    ('FALTA DE VALOR NA TABELA', 'FALTA DE VALOR NA TABELA'),
                    ('FALTA TABELA DE CONTRASTE', 'FALTA TABELA DE CONTRASTE'),
                    ('OUTROS', 'OUTROS'),
                ],
                default='PENDENTE',
                max_length=40,
                verbose_name='Status Conferência',
            ),
        ),
    ]
