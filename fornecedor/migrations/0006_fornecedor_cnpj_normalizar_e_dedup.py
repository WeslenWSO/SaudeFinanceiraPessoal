import re

from django.db import migrations


def _digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def normalizar_cnpj_somente_digitos(apps, schema_editor):
    Fornecedor = apps.get_model("fornecedor", "Fornecedor")
    for f in Fornecedor.objects.iterator():
        d = _digitos(f.cnpj)
        if len(d) == 14 and f.cnpj != d:
            f.cnpj = d
            f.save(update_fields=["cnpj"])


def remover_fornecedores_duplicados_mesmo_cnpj(apps, schema_editor):
    """Mantém o registro com menor id por (empresa_id, cnpj)."""
    Fornecedor = apps.get_model("fornecedor", "Fornecedor")
    vistos = set()
    excluir = []
    for f in Fornecedor.objects.order_by("id"):
        chave = (f.empresa_id, f.cnpj)
        if chave in vistos:
            excluir.append(f.pk)
        else:
            vistos.add(chave)
    if excluir:
        Fornecedor.objects.filter(pk__in=excluir).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("fornecedor", "0005_fornecedor_atividades_cnae_fornecedor_bairro_and_more"),
    ]

    operations = [
        migrations.RunPython(normalizar_cnpj_somente_digitos, migrations.RunPython.noop),
        migrations.RunPython(remover_fornecedores_duplicados_mesmo_cnpj, migrations.RunPython.noop),
    ]
