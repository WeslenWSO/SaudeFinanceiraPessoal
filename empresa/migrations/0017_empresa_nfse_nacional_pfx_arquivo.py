import os
import uuid

from django.db import migrations, models


def _empresa_pfx_nacional_upload_to(instance, filename: str) -> str:
    ext = (os.path.splitext(filename)[1] or ".pfx").lower()
    if ext not in (".pfx", ".p12"):
        ext = ".pfx"
    ident = instance.pk if instance.pk else uuid.uuid4().hex[:16]
    return f"empresa/certificados/{ident}/certificado{ext}"


class Migration(migrations.Migration):

    dependencies = [
        ("empresa", "0016_empresa_sicoob_mtls_usar_pfx_nfse"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="nfse_nacional_pfx_arquivo",
            field=models.FileField(
                blank=True,
                help_text="Envie o arquivo pelo navegador; fica salvo no servidor (pasta media/).",
                max_length=500,
                upload_to=_empresa_pfx_nacional_upload_to,
                verbose_name="Certificado digital (.pfx)",
            ),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="nfse_nacional_pfx_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Somente se o .pfx já estiver em disco neste servidor (ex.: path Linux). "
                "Se enviar arquivo acima, este campo pode ficar em branco.",
                max_length=500,
                verbose_name="Caminho absoluto no servidor (alternativa ao arquivo acima)",
            ),
        ),
    ]
