# Campos NFS-e nacional no cadastro da empresa.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0012_socio"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_base_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Vazio usa NFSE_NACIONAL_BASE_URL do servidor. Ex.: https://sefin.nfse.gov.br ou https://sefin.producaorestrita.nfse.gov.br",
                max_length=255,
                verbose_name="URL base SEFIN (NFS-e nacional)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_pfx_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Alternativa a NFSE_NACIONAL_PFX_PATH no ambiente.",
                max_length=500,
                verbose_name="Caminho absoluto do certificado (.pfx)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_pfx_senha_cifrada",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                verbose_name="Senha do PFX (cifrada)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_cert_validade",
            field=models.DateField(
                blank=True,
                help_text="Preenchida automaticamente ao validar o PFX com a senha.",
                null=True,
                verbose_name="Validade do certificado (fim)",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_thumbprint_sha1",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Opcional: preenchido ao escolher certificado na busca no Windows.",
                max_length=40,
                verbose_name="Thumbprint SHA1 (referência Windows)",
            ),
        ),
    ]
