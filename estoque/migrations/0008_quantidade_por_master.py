from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0007_alter_requisicaoestoque_setor_consumo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='entradaestoquenota',
            name='quantidade_por_master',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name='produtoestoque',
            name='quantidade_por_master',
            field=models.DecimalField(
                decimal_places=3,
                default=0,
                help_text='Quantas unidades de consumo vêm em 1 unidade master (ex.: 1 PCT = 4 UN → informe 4).',
                max_digits=14,
                verbose_name='Unidades por master',
            ),
        ),
    ]
