# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cliente", "0003_cliente_descricao_extrato_bancario"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="codigo_externo",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Usado na pasta ao salvar cópia do XML da NFSe (prestador): código-razão do tomador.",
                max_length=50,
                verbose_name="Código externo",
            ),
        ),
    ]
