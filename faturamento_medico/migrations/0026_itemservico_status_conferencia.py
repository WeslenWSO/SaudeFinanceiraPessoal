from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0025_faturamentomedico_campos_agenda_ris'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='status_conferencia',
            field=models.CharField(
                blank=True,
                choices=[
                    ('CONFERIDO', 'CONFERIDO'),
                    ('FALTA DE GUIA', 'FALTA DE GUIA'),
                    ('FALTA DE VALOR NA TABELA', 'FALTA DE VALOR NA TABELA'),
                    ('OUTROS', 'OUTROS'),
                    ('PENDENTE', 'PENDENTE'),
                ],
                default='PENDENTE',
                max_length=40,
                verbose_name='Status Conferência',
            ),
        ),
    ]
