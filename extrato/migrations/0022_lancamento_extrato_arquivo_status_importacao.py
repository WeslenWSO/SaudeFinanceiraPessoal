# Generated manually for extrato_arquivo and status_importacao on Lancamento

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0021_lancamento_lancamento_origem_transferencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='lancamento',
            name='extrato_arquivo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lancamentos_importados',
                to='extrato.extratoarquivo',
            ),
        ),
        migrations.AddField(
            model_name='lancamento',
            name='status_importacao',
            field=models.CharField(
                choices=[
                    ('P', 'Pendente (prévia)'),
                    ('I', 'Importado'),
                    ('D', 'Duplicado'),
                    ('X', 'Ignorado'),
                ],
                db_index=True,
                default='I',
                max_length=1,
            ),
        ),
    ]
