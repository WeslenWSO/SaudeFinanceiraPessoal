from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orcamento_compra', '0003_orcamentocomprafornecedor_pdf_linhas'),
    ]

    operations = [
        migrations.AddField(
            model_name='orcamentocompraitem',
            name='codigo_produto_comercio',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                max_length=50,
                verbose_name='Código produto (NF comércio)',
            ),
        ),
    ]
