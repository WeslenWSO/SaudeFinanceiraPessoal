from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0026_itemservico_status_conferencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='nome_associado',
            field=models.CharField(
                blank=True,
                max_length=200,
                null=True,
                verbose_name='Nome do Associado',
            ),
        ),
    ]
