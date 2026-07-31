from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servicos_medicos', '0004_alter_tabelapreco_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tabelapreco',
            name='preco_apartamento',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                verbose_name='Preço sem Contraste',
            ),
        ),
        migrations.AlterField(
            model_name='tabelapreco',
            name='preco_enfermaria',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                verbose_name='Preço com Contraste',
            ),
        ),
    ]
