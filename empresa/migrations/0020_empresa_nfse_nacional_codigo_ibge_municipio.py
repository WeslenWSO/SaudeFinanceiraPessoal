# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0019_empresa_nfse_xml_pasta_prestador_tomador"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_codigo_ibge_municipio",
            field=models.CharField(
                blank=True,
                default="",
                help_text="7 dígitos do município emissor (DPS). Usado para pré-preencher consulta por DPS no portal nacional.",
                max_length=7,
                verbose_name="Código IBGE do município (NFS-e nacional)",
            ),
        ),
    ]
