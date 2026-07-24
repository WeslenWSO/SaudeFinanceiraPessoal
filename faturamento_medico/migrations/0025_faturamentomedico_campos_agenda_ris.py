from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0024_itemservico_com_contraste'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='horario_inicio',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Horário de Início'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='horario_fim',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Horário de Fim'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='prioridade',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Prioridade'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='motivo_cancelamento',
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name='Motivo Cancelamento/Desistência/Deleção',
            ),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='medico_solicitante',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Médico Solicitante'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='tecnico',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Técnico'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='checkin_por',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Check-in Por'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='agendado_por',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Agendado Por'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='tag',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Tag'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='indicacao_clinica',
            field=models.TextField(blank=True, null=True, verbose_name='Indicação Clínica'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='descricao',
            field=models.TextField(blank=True, null=True, verbose_name='Descrição'),
        ),
    ]
