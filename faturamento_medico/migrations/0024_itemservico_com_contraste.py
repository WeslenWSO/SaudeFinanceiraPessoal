from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0023_faturamentomedico_cpf_horario_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemservico',
            name='com_contraste',
            field=models.BooleanField(default=False, verbose_name='Com Contraste'),
        ),
    ]
