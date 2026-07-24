from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0013_empresa_nfse_nacional_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="sicoob_client_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Vazio usa SICOOB_CLIENT_ID do servidor.",
                max_length=80,
                verbose_name="Sicoob — Client ID (app no portal desenvolvedor)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="sicoob_chave_acesso",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Enviada como username no token OAuth. Vazio usa SICOOB_CHAVE_ACESSO / SICOOB_USERNAME no servidor.",
                max_length=255,
                verbose_name="Sicoob — Chave de acesso (PJ) ou usuário (PF)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="sicoob_senha_cifrada",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="Preenchida pelo formulário ao salvar.",
                verbose_name="Sicoob — Senha (cifrada)",
            ),
        ),
    ]
