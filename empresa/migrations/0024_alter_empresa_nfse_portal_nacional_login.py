# Generated manually — help_text do login do portal nacional (URL Emissor Nacional).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0023_empresa_nfse_portal_nacional_login_senha"),
    ]

    operations = [
        migrations.AlterField(
            model_name="empresa",
            name="nfse_portal_nacional_login",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "CPF, CNPJ ou e-mail usado em https://www.nfse.gov.br/EmissorNacional/Login "
                    "(usuário/senha, certificado ou Gov.br). Referência para quem opera o navegador ou "
                    "extensões de download; não substitui o certificado da API SEFIN."
                ),
                max_length=255,
                verbose_name="Portal nacional (nfse.gov.br) — login",
            ),
        ),
    ]
