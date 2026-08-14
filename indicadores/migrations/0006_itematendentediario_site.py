from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0005_lancamento_completo'),
    ]

    operations = [
        migrations.AddField(
            model_name='itematendentediario',
            name='site',
            field=models.PositiveIntegerField(default=0, verbose_name='Site'),
        ),
    ]
