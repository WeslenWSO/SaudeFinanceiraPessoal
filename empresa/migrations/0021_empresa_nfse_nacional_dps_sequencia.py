# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0020_empresa_nfse_nacional_codigo_ibge_municipio"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_dps_proximo_numero",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Quando o número for deixado em branco no portal, usa este valor e avança +1 após cada tentativa que retornar nota (importada ou já existente). Vazio = começa em 1.",
                null=True,
                verbose_name="Próximo número da DPS (portal nacional)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_dps_serie_padrao",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Usada na consulta DPS quando a série for deixada em branco no portal. Ex.: 80000. Se vazio, o sistema usa 80000.",
                max_length=8,
                verbose_name="Série DPS padrão (portal nacional)",
            ),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="nfse_nacional_codigo_ibge_municipio",
            field=models.CharField(
                blank=True,
                default="",
                help_text="7 dígitos do município emissor (DPS). Obrigatório para usar “Importar NFSe — Portal Nacional” (o IBGE não é digitado naquela tela).",
                max_length=7,
                verbose_name="Código IBGE do município (NFS-e nacional)",
            ),
        ),
    ]
