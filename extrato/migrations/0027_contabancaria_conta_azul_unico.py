from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0026_contabancaria_conta_azul_id'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='contabancaria',
            constraint=models.UniqueConstraint(
                condition=models.Q(('conta_azul_id__gt', '')),
                fields=('empresa', 'conta_azul_id'),
                name='conta_bancaria_conta_azul_unico',
            ),
        ),
    ]
