from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0025_empresa_integracao_conta_azul'),
    ]

    operations = [
        migrations.AlterField(
            model_name='empresa',
            name='razao',
            field=models.CharField(max_length=150, verbose_name='Razao'),
        ),
    ]
