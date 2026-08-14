from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


PREMIACAO_PADRAO = {
    'NPS GERAL': (Decimal('30.00'), Decimal('15.00')),
    'NPS MUSCULAÇÃO': (Decimal('80.00'), Decimal('40.00')),
    'NPS POR HORA': (Decimal('30.00'), Decimal('15.00')),
    'MONTAGEM DE TREINO': (Decimal('30.00'), Decimal('15.00')),
    'CHURN': (Decimal('30.00'), Decimal('15.00')),
}


def aplicar_premiacao_padrao(apps, schema_editor):
    Indicador = apps.get_model('indicadores', 'Indicador')
    for nome, (prem, prop) in PREMIACAO_PADRAO.items():
        Indicador.objects.filter(nome=nome, area='MUSCULACAO').update(
            premiacao=prem,
            proporcao=prop,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0002_seed_indicadores_padrao'),
    ]

    operations = [
        migrations.AddField(
            model_name='indicador',
            name='premiacao',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Premiação (R$)'),
        ),
        migrations.AddField(
            model_name='indicador',
            name='proporcao',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5, verbose_name='Proporção (%)'),
        ),
        migrations.CreateModel(
            name='PeriodoAcademia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ano', models.PositiveIntegerField(verbose_name='Ano')),
                ('mes', models.PositiveIntegerField(verbose_name='Mês')),
                ('data_referencia', models.DateField(blank=True, null=True, verbose_name='Data dos dados')),
                ('qt_ativos', models.PositiveIntegerField(default=0, verbose_name='Qt. ativos')),
                ('qt_cancelados', models.PositiveIntegerField(default=0, verbose_name='Qt. cancelados')),
                ('churn_pct', models.DecimalField(decimal_places=4, default=Decimal('0.0000'), editable=False, max_digits=7, verbose_name='Churn (%)')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='periodos_academia', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Período academia',
                'verbose_name_plural': 'Períodos academia',
                'ordering': ['-ano', '-mes'],
                'unique_together': {('empresa', 'ano', 'mes')},
            },
        ),
        migrations.CreateModel(
            name='ItemPeriodoAcademia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('meta', models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, verbose_name='Meta')),
                ('resultado', models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, verbose_name='Resultado')),
                ('indicador', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens_periodo', to='indicadores.indicador', verbose_name='Indicador')),
                ('periodo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens', to='indicadores.periodoacademia', verbose_name='Período')),
            ],
            options={
                'verbose_name': 'Item do período',
                'verbose_name_plural': 'Itens do período',
                'ordering': ['indicador__area', 'indicador__ordem', 'indicador__nome'],
                'unique_together': {('periodo', 'indicador')},
            },
        ),
        migrations.RunPython(aplicar_premiacao_padrao, migrations.RunPython.noop),
    ]
