from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0014_empresa_sicoob_api"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="sicoob_client_secret_cifrada",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="Opcional: apps confidenciais no portal. Preenchido pelo formulário ao salvar.",
                verbose_name="Sicoob — Client Secret (cifrado)",
            ),
        ),
    ]
