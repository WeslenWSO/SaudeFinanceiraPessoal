from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0022_faturamentomedico_agendado_via'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='cpf',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='CPF'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='horario',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Horário'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='status_agendamento',
            field=models.CharField(
                blank=True,
                max_length=50,
                null=True,
                verbose_name='Status do Agendamento',
            ),
        ),
    ]
