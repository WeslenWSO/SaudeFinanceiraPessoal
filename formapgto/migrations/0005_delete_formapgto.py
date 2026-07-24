# Remove modelo FormaPgto e tabela formapgto_formapgto do banco

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('formapgto', '0004_alter_formapgto_options_formapgto_empresa_and_more'),
        ('contasapagar', '0013_remove_contasapagar_formapgto'),
        ('notafiscalentrada', '0006_alter_notafiscalentrada_forma_pagamento_cobranca'),
        ('regraConciliacao', '0008_alter_regraconciliacao_forma_pagamento_cobranca'),
    ]

    operations = [
        migrations.DeleteModel(
            name='FormaPgto',
        ),
    ]
