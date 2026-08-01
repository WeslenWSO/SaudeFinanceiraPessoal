from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('categoria', '0010_categoria_conta_azul_id_centrocusto'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoria',
            name='bloquear_sync_conta_azul',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Marcado: a reimportação do Conta Azul não altera nome, tipo, grupo, '
                    'classificação nem sintético desta categoria.'
                ),
                verbose_name='Manter configuração local na sync Conta Azul',
            ),
        ),
    ]
