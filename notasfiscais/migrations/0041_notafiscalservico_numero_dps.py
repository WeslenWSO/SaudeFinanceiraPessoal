# Generated manually — número da DPS (SPED) para sugerir na tela Portal Nacional

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notasfiscais", "0040_lognotafiscal"),
    ]

    operations = [
        migrations.AddField(
            model_name="notafiscalservico",
            name="numero_dps",
            field=models.CharField(
                blank=True,
                help_text="Número da DPS no XML nacional (nDPS); não é o nNFSe impresso no DANFSE.",
                max_length=20,
                null=True,
                verbose_name="Número da DPS",
            ),
        ),
    ]
