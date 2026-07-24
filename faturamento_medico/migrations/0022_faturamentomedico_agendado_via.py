from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0021_itemservico_modalidade_conferido'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='agendado_via',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Agendado Via'),
        ),
    ]
