from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0021_empresa_nfse_nacional_dps_sequencia"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_adn_data_ultima_sincronizacao",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="ADN — data/hora da última sincronização",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_adn_ultimo_nsu",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Controle da sincronização ADN por empresa. Em branco começa do NSU 0 (primeira carga). Depois da sincronização, o sistema atualiza automaticamente.",
                null=True,
                verbose_name="ADN — último NSU integrado",
            ),
        ),
    ]
