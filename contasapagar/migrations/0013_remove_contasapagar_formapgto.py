# Remove campo formapgto; usar apenas cobranca

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contasapagar', '0012_contasapagar_cpf_cnpj'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contasapagar',
            name='formapgto',
        ),
    ]
