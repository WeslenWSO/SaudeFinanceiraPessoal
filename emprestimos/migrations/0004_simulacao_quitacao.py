# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('emprestimos', '0003_emprestimo_banco'),
    ]

    operations = [
        migrations.CreateModel(
            name='SimulacaoQuitacaoEmprestimo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(blank=True, default='', help_text='Opcional — facilita a pesquisa.', max_length=200, verbose_name='Título / observação')),
                ('data_quitacao', models.DateField(verbose_name='Data pretendida de quitação')),
                ('metodo', models.CharField(blank=True, default='', max_length=20, verbose_name='Método')),
                ('indicador_rotulo', models.CharField(blank=True, default='', max_length=100)),
                ('parcelas_numeros', models.CharField(blank=True, default='', help_text='Ex.: 19,20,21', max_length=500, verbose_name='Nºs das parcelas')),
                ('qtd_parcelas', models.PositiveIntegerField(default=0)),
                ('total_amortizacao', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15)),
                ('total_juros_extrato', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15)),
                ('juros_calculado', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15)),
                ('valor_quitacao', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15)),
                ('dias_juros', models.PositiveIntegerField(default=0)),
                ('data_referencia', models.DateField(blank=True, null=True)),
                ('data_fim_juros', models.DateField(blank=True, null=True)),
                ('parcelas_restantes', models.PositiveIntegerField(default=0)),
                ('saldo_restante_amort', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15)),
                ('detalhes_json', models.TextField(blank=True, default='', verbose_name='Detalhes (JSON)')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='simulacoes_quitacao_emprestimo', to=settings.AUTH_USER_MODEL)),
                ('emprestimo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='simulacoes_quitacao', to='emprestimos.emprestimo', verbose_name='Empréstimo')),
            ],
            options={
                'verbose_name': 'Simulação de quitação',
                'verbose_name_plural': 'Simulações de quitação',
                'ordering': ['-criado_em'],
            },
        ),
    ]
