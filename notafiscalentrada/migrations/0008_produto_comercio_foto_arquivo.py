from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notafiscalentrada', '0007_produto_comercio_foto'),
    ]

    operations = [
        migrations.AddField(
            model_name='produtocomerciofoto',
            name='imagem',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='produto_comercio/%Y/%m/',
                verbose_name='Arquivo da imagem',
            ),
        ),
        migrations.AlterField(
            model_name='produtocomerciofoto',
            name='url_imagem',
            field=models.URLField(blank=True, default='', max_length=600),
        ),
    ]
