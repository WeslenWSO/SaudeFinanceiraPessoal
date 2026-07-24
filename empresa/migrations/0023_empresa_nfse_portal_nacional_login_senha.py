from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0022_empresa_adn_ultimo_nsu"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_portal_nacional_login",
            field=models.CharField(
                blank=True,
                default="",
                help_text="CPF, CNPJ ou e-mail usado no acesso ao site do Portal Nacional da NFS-e (login gov.br / credenciais do portal). Referência para quem opera o navegador ou extensões de download; não substitui o certificado da API SEFIN.",
                max_length=255,
                verbose_name="Portal nacional (nfse.gov.br) — login",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_portal_nacional_senha_cifrada",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="Preenchida pelo formulário ao salvar (mesma criptografia da senha do PFX).",
                verbose_name="Portal nacional — senha (cifrada)",
            ),
        ),
    ]
