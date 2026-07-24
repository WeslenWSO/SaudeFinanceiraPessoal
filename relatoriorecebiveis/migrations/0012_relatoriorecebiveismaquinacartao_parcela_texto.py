# Generated manually for campo Parcela (texto ex.: 1 / 2)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('relatoriorecebiveis', '0011_alter_relatoriorecebiveismaquinacartao_numero_autorizacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='relatoriorecebiveismaquinacartao',
            name='parcela_texto',
            field=models.CharField(
                blank=True,
                help_text='Texto como no relatório (ex.: 1 / 2). Opcional; parcelas e total_parcelas podem ser derivados.',
                max_length=40,
                null=True,
                verbose_name='Parcela',
            ),
        ),
    ]
