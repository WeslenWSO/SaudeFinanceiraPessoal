from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0003_periodo_academia'),
    ]

    operations = [
        migrations.CreateModel(
            name='LancamentoVendasDiario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateField(verbose_name='Dia')),
                ('balcao', models.PositiveIntegerField(default=0, verbose_name='Balcão')),
                ('site', models.PositiveIntegerField(default=0, verbose_name='Site')),
                ('total_dia', models.PositiveIntegerField(default=0, editable=False, verbose_name='Total dia')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lancamentos_vendas_diario', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Lançamento vendas (dia)',
                'verbose_name_plural': 'Lançamentos vendas (dia)',
                'ordering': ['-data'],
                'unique_together': {('empresa', 'data')},
            },
        ),
    ]
