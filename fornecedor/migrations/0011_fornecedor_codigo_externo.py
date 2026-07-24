# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fornecedor", "0010_fornecedor_descricao_extrato_bancario"),
    ]

    operations = [
        migrations.AddField(
            model_name="fornecedor",
            name="codigo_externo",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Usado na pasta ao salvar cópia do XML da NFSe (tomador): código-razão do prestador.",
                max_length=50,
                verbose_name="Código externo",
            ),
        ),
    ]
