from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0015_empresa_sicoob_client_secret_cifrada"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="sicoob_mtls_usar_pfx_nfse",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Se marcado, token e API de extrato Sicoob enviam o certificado cliente (mTLS) usando o "
                    "mesmo arquivo .pfx e senha já cadastrados para a NFS-e nacional desta empresa."
                ),
                verbose_name="Sicoob — mTLS com o mesmo PFX da NFS-e nacional",
            ),
        ),
    ]
