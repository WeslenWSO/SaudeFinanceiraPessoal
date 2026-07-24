# Recria notasfiscais_lognotafiscal após DeleteModel em 0037 (modelo voltou em models.py).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('notasfiscais', '0039_merge_0036_0038'),
        ('empresa', '0001_initial'),
        ('cobranca', '0001_initial'),
        ('socio', '0001_initial'),
        ('regraImposto', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LogNotaFiscal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_nota', models.CharField(max_length=20, verbose_name='Número da Nota')),
                ('serie', models.CharField(blank=True, max_length=10, null=True, verbose_name='Série')),
                ('data_emissao', models.DateField(default=django.utils.timezone.now, verbose_name='Data de Emissão')),
                ('cnpj_cpf', models.CharField(max_length=18, verbose_name='CNPJ/CPF')),
                ('cliente', models.CharField(max_length=200, verbose_name='Cliente')),
                ('valor_bruto', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Valor Bruto')),
                ('valor_liquido', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Valor Líquido')),
                ('valor_deducoes', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor Deduções')),
                ('valor_pis', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor PIS')),
                ('valor_cofins', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor COFINS')),
                ('valor_inss', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor INSS')),
                ('valor_ir', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor IR')),
                ('valor_csll', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor CSLL')),
                ('iss_retido', models.BooleanField(default=False, verbose_name='ISS Retido')),
                ('valor_iss_retido', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor ISS Retido')),
                ('outras_retencoes', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Outras Retenções')),
                ('aliquota', models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Alíquota (%)')),
                ('discriminacao', models.TextField(blank=True, null=True, verbose_name='Discriminação')),
                ('observacoes', models.TextField(blank=True, null=True, verbose_name='Observações')),
                ('segmento', models.CharField(blank=True, max_length=100, null=True, verbose_name='Segmento')),
                (
                    'base_servico',
                    models.CharField(
                        choices=[('NORMAL', 'Normal'), ('DEMAIS', 'Demais')],
                        default='NORMAL',
                        max_length=10,
                        verbose_name='Base Serviço',
                    ),
                ),
                ('nsu', models.CharField(blank=True, max_length=100, null=True, verbose_name='NSU')),
                (
                    'status_conciliacao',
                    models.CharField(
                        blank=True,
                        choices=[
                            ('nao_conciliado', 'Não Conciliado'),
                            ('conciliado', 'Conciliado'),
                            ('parcialmente_conciliado', 'Parcialmente Conciliado'),
                        ],
                        default='nao_conciliado',
                        max_length=30,
                        null=True,
                        verbose_name='Status de Conciliação',
                    ),
                ),
                ('issapuracao', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Iss Apuração')),
                ('pisapuracao', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Pis Apuração')),
                ('cofinsapuracao', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Cofins Apuração')),
                ('csllapuracao', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Csll Apuração')),
                ('irpjapuracao', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Irpj Apuração')),
                ('irpjadicional', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Irpj Adicional')),
                (
                    'motivo_exclusao',
                    models.CharField(blank=True, default='segmentacao', max_length=100, verbose_name='Motivo da Exclusão'),
                ),
                ('data_segmentacao', models.DateTimeField(auto_now_add=True, verbose_name='Data da Segmentação')),
                (
                    'codigo_da_regra_do_imposto',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to='regraImposto.regraimposto',
                        verbose_name='Código da Regra do Imposto',
                    ),
                ),
                (
                    'empresa',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='empresa.empresa',
                        verbose_name='Empresa',
                    ),
                ),
                (
                    'forma_pagamento',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to='cobranca.cobranca',
                        verbose_name='Forma de Pagamento',
                    ),
                ),
                (
                    'socio',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to='socio.socio',
                        verbose_name='Sócio Responsável',
                    ),
                ),
                (
                    'usuario_segmentacao',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Usuário que segmentou',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Log Nota Fiscal',
                'verbose_name_plural': 'Logs Notas Fiscais',
                'ordering': ['-data_segmentacao', '-numero_nota'],
            },
        ),
    ]
