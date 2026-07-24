# Alterar forma_pagamento de FormaPgto para Cobranca

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cobranca', '0001_initial'),
        ('regraConciliacao', '0007_alter_regraconciliacao_categoria_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='regraconciliacao',
            name='forma_pagamento',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='cobranca.cobranca', verbose_name='Forma de Pagamento'),
        ),
    ]
