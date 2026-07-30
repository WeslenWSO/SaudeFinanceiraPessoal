from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0001_initial'),
        ('faturamento_medico', '0028_alter_itemservico_status_conferencia'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExtratoPagamentoConvenio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('competencia', models.CharField(blank=True, default='', max_length=7, verbose_name='Competência')),
                ('convenio', models.CharField(blank=True, default='', max_length=100, verbose_name='Convênio')),
                ('data_lote', models.DateField(blank=True, null=True, verbose_name='Data do Lote')),
                ('lote', models.CharField(blank=True, default='', max_length=50, verbose_name='Lote')),
                ('protocolo', models.CharField(blank=True, default='', max_length=50, verbose_name='Protocolo')),
                ('qt_guias', models.PositiveIntegerField(blank=True, null=True, verbose_name='Qt de Guia')),
                ('valor', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Valor')),
                ('valor_processado', models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, verbose_name='Valor Processado')),
                ('valor_glosado', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Valor Glosado')),
                ('valor_liberado', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Valor Liberado')),
                ('observacao', models.TextField(blank=True, default='', verbose_name='Observação')),
                ('nota', models.CharField(blank=True, default='', max_length=50, verbose_name='Nota')),
                ('valor_nota', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Valor da Nota')),
                ('retencoes', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Retenções')),
                ('liquido', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Líquido')),
                ('data_previsao', models.DateField(blank=True, null=True, verbose_name='Data de Previsão')),
                ('data_recebimento', models.DateField(blank=True, null=True, verbose_name='Data de Recebimento')),
                ('valor_recebido', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Valor Recebido')),
                ('banco', models.CharField(blank=True, default='', max_length=100, verbose_name='Banco')),
                ('numero_demonstrativo', models.CharField(blank=True, default='', max_length=50, verbose_name='Nº Demonstrativo')),
                ('nome_arquivo', models.CharField(blank=True, default='', max_length=255, verbose_name='Arquivo origem')),
                ('data_criacao', models.DateTimeField(auto_now_add=True)),
                ('data_atualizacao', models.DateTimeField(auto_now=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Extrato de Pagamento — Convênio',
                'verbose_name_plural': 'Extratos de Pagamento — Convênio',
                'ordering': ['-data_recebimento', '-competencia', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='extratopagamentoconvenio',
            constraint=models.UniqueConstraint(
                fields=('empresa', 'competencia', 'protocolo', 'lote', 'data_recebimento', 'valor', 'valor_liberado'),
                name='uniq_extrato_pagamento_convenio',
            ),
        ),
    ]
