from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def seed_atendentes(apps, schema_editor):
    Empresa = apps.get_model('empresa', 'Empresa')
    AtendenteAcademia = apps.get_model('indicadores', 'AtendenteAcademia')
    nomes = ['LUCIMEIRE', 'MARIANY', 'NATÁLIA', 'LUANA']
    for empresa in Empresa.objects.all().iterator():
        for ordem, nome in enumerate(nomes, start=1):
            AtendenteAcademia.objects.get_or_create(
                empresa_id=empresa.id,
                nome=nome,
                defaults={'ordem': ordem, 'ativo': True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0004_lancamentovendasdiario'),
    ]

    operations = [
        migrations.CreateModel(
            name='AtendenteAcademia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=120, verbose_name='Nome')),
                ('ordem', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='atendentes_academia', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Atendente (academia)',
                'verbose_name_plural': 'Atendentes (academia)',
                'ordering': ['ordem', 'nome'],
                'unique_together': {('empresa', 'nome')},
            },
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='cancel_inadimplentes',
            field=models.PositiveIntegerField(default=0, verbose_name='Inadimplentes'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='cancel_negassist',
            field=models.PositiveIntegerField(default=0, verbose_name='Neg. assist.'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='cancel_solicitados',
            field=models.PositiveIntegerField(default=0, verbose_name='Solicitados'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='churn_dia',
            field=models.DecimalField(decimal_places=4, default=Decimal('0.0000'), editable=False, max_digits=7, verbose_name='Churn dia (%)'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='conversao_balcao_pct',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), editable=False, max_digits=7, verbose_name='Conversão balcão (%)'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='oport_balcao',
            field=models.PositiveIntegerField(default=0, verbose_name='Oport. balcão'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='saldo_comercial',
            field=models.IntegerField(default=0, editable=False, verbose_name='Saldo comercial'),
        ),
        migrations.AddField(
            model_name='lancamentovendasdiario',
            name='total_cancel_dia',
            field=models.PositiveIntegerField(default=0, editable=False, verbose_name='Total cancel. dia'),
        ),
        migrations.AlterField(
            model_name='lancamentovendasdiario',
            name='total_dia',
            field=models.PositiveIntegerField(default=0, editable=False, verbose_name='Total vendas dia'),
        ),
        migrations.CreateModel(
            name='ItemAtendenteDiario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('oport', models.PositiveIntegerField(default=0, verbose_name='Oport.')),
                ('vendas', models.PositiveIntegerField(default=0, verbose_name='Vendas')),
                ('cancel', models.PositiveIntegerField(default=0, verbose_name='Cancel.')),
                ('atendente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lancamentos_dia', to='indicadores.atendenteacademia', verbose_name='Atendente')),
                ('lancamento', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens_atendente', to='indicadores.lancamentovendasdiario', verbose_name='Lançamento')),
            ],
            options={
                'verbose_name': 'Atendente no dia',
                'verbose_name_plural': 'Atendentes no dia',
                'ordering': ['atendente__ordem', 'atendente__nome'],
                'unique_together': {('lancamento', 'atendente')},
            },
        ),
        migrations.RunPython(seed_atendentes, migrations.RunPython.noop),
    ]
