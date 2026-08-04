from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0031_medcloud_integration'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='data_recorrencia',
            field=models.DateField(blank=True, null=True, verbose_name='Data da Recorrência'),
        ),
        migrations.AddField(
            model_name='itemservico',
            name='valor_glosa',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor da Glosa'),
        ),
    ]
