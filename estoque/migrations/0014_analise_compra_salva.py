import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orcamento_compra', '0004_orcamentocompraitem_codigo_produto_comercio'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('estoque', '0013_setor_maleta'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnaliseCompraSalva',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('observacao', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('criado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='analises_compra_criadas',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='analises_compra_salvas',
                    to='empresa.empresa',
                )),
                ('orcamento_gerado', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='analises_compra_origem',
                    to='orcamento_compra.orcamentocompra',
                    verbose_name='Orçamento gerado',
                )),
            ],
            options={
                'verbose_name': 'Análise de compra salva',
                'verbose_name_plural': 'Análises de compra salvas',
                'ordering': ['-atualizado_em', '-id'],
            },
        ),
        migrations.CreateModel(
            name='AnaliseCompraSalvaItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo_produto', models.CharField(max_length=50)),
                ('descricao', models.CharField(max_length=300)),
                ('marca', models.CharField(blank=True, default='', max_length=120)),
                ('fornecedor_texto', models.CharField(blank=True, default='', max_length=200)),
                ('qtd_ultima_compra', models.DecimalField(
                    blank=True, decimal_places=3, max_digits=14, null=True,
                )),
                ('data_ultima_compra', models.DateField(blank=True, null=True)),
                ('estoque_registrado', models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ('unidade', models.CharField(blank=True, default='', max_length=20)),
                ('unidade_master', models.CharField(blank=True, default='', max_length=20)),
                ('qtd_master', models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ('dias_entrega', models.PositiveIntegerField(blank=True, null=True)),
                ('quantidade_desejada', models.DecimalField(
                    decimal_places=3,
                    default=0,
                    max_digits=14,
                    verbose_name='Quantidade desejada',
                )),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('analise', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='itens',
                    to='estoque.analisecomprasalva',
                )),
                ('produto', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='itens_analise_compra',
                    to='estoque.produtoestoque',
                )),
            ],
            options={
                'verbose_name': 'Item da análise de compra',
                'verbose_name_plural': 'Itens da análise de compra',
                'ordering': ['ordem', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='analisecomprasalvaitem',
            constraint=models.UniqueConstraint(
                fields=('analise', 'produto'),
                name='analise_compra_item_produto_unico',
            ),
        ),
    ]
