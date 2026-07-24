from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0020_alter_faturamentomedico_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='modalidade',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Modalidade'),
        ),
        migrations.AddField(
            model_name='itemservico',
            name='conferido',
            field=models.BooleanField(default=False, verbose_name='Conferência'),
        ),
    ]
