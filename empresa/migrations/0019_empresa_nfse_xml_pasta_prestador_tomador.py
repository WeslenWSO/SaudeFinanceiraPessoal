# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0018_alter_empresa_nfse_nacional_pfx_arquivo"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_xml_pasta_prestador",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Raiz quando a empresa é o prestador no XML. Subpastas: código externo-razão do tomador / "
                    "competência (MMYYYY) / arquivo.xml. Vazio usa NFSE_XML_COPIA_PRESTADOR no servidor."
                ),
                max_length=500,
                verbose_name="Pasta cópias XML NFSe (prestador)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_xml_pasta_tomador",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Raiz quando a empresa é o tomador no XML. Subpastas: código externo-razão do prestador / "
                    "competência (MMYYYY) / arquivo.xml. Vazio usa NFSE_XML_COPIA_TOMADOR no servidor."
                ),
                max_length=500,
                verbose_name="Pasta cópias XML NFSe (tomador)",
            ),
        ),
    ]
