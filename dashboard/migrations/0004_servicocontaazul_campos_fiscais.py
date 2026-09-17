from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_servico_conta_azul'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicocontaazul',
            name='aliquota_ibs_municipal',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Somente leitura — calculada pelo Conta Azul.',
                max_digits=7,
                null=True,
                verbose_name='Alíquota IBS municipal (%)',
            ),
        ),
        migrations.AddField(
            model_name='servicocontaazul',
            name='codigo_servico_municipal',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Código serviço municipal'),
        ),
        migrations.AddField(
            model_name='servicocontaazul',
            name='natureza_operacao',
            field=models.CharField(blank=True, default='', max_length=80, verbose_name='Natureza de operação'),
        ),
        migrations.AlterField(
            model_name='servicocontaazul',
            name='aliquota_ibs',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Somente leitura — calculada pelo Conta Azul.',
                max_digits=7,
                null=True,
                verbose_name='Alíquota IBS estadual (%)',
            ),
        ),
        migrations.AlterField(
            model_name='servicocontaazul',
            name='codigo_nbs',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex.: 1.2301.22.00',
                max_length=30,
                verbose_name='NBS (cNBS)',
            ),
        ),
        migrations.AlterField(
            model_name='servicocontaazul',
            name='c_class_trib',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Código de Classificação Tributária (Reforma Tributária). Ex.: 000001',
                max_length=20,
                verbose_name='cClassTrib',
            ),
        ),
        migrations.AlterField(
            model_name='servicocontaazul',
            name='indicador_operacao',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex.: 030101',
                max_length=20,
                verbose_name='Indicador da operação',
            ),
        ),
    ]
