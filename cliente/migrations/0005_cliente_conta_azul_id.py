from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cliente', '0004_cliente_codigo_externo'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='conta_azul_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                max_length=36,
                verbose_name='ID Conta Azul',
            ),
        ),
        migrations.AddConstraint(
            model_name='cliente',
            constraint=models.UniqueConstraint(
                condition=models.Q(('conta_azul_id__gt', '')),
                fields=('empresa', 'conta_azul_id'),
                name='cliente_conta_azul_unico',
            ),
        ),
    ]
