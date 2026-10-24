from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0005_produto_fornecedor'),
    ]

    operations = [
        migrations.AddField(
            model_name='produtoestoque',
            name='natureza',
            field=models.CharField(
                choices=[
                    ('consumivel', 'Consumível (farmácia / materiais)'),
                    ('imobilizado', 'Imobilizado'),
                ],
                default='consumivel',
                help_text='Consumível: farmácia e requisições. Imobilizado: patrimônio / bens.',
                max_length=16,
                verbose_name='Natureza',
            ),
        ),
    ]
