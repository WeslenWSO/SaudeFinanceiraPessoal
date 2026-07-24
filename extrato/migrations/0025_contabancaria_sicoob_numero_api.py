from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("extrato", "0024_contabancaria_saldo_inicial_data_inicial_saldo"),
    ]

    operations = [
        migrations.AddField(
            model_name="contabancaria",
            name="sicoob_numero_conta_corrente_api",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Somente dígitos, conforme exibido no app do desenvolvedor Sicoob para consulta de extrato.",
                max_length=32,
                verbose_name="Sicoob — Nº conta API (extrato)",
            ),
        ),
    ]
