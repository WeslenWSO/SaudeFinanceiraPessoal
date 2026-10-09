from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orcamento_compra', '0002_orcamentocompraresultadovencedor_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='orcamentocomprafornecedor',
            name='pdf_linhas',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de itens detectados no PDF e vínculo com itens do orçamento.',
                verbose_name='Linhas do PDF (de-para)',
            ),
        ),
    ]
