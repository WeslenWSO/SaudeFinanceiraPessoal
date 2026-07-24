# Alterar forma_pagamento de FormaPgto para Cobranca

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cobranca', '0001_initial'),
        ('notafiscalentrada', '0005_remove_notafiscalentrada_regra_rateio'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notafiscalentrada',
            name='forma_pagamento',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='cobranca.cobranca', verbose_name='Forma de Pagamento'),
        ),
    ]
