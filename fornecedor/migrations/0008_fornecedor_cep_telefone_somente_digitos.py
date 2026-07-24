import re

from django.db import migrations


def _digitos(valor, max_len=None):
    d = re.sub(r"\D", "", str(valor or ""))
    if max_len is not None:
        return d[:max_len]
    return d


def forwards(apps, schema_editor):
    Fornecedor = apps.get_model("fornecedor", "Fornecedor")
    for row in Fornecedor.objects.iterator():
        new_cep = _digitos(row.cep, 8)
        new_tel = _digitos(row.telefone, 11)
        if row.cep != new_cep or row.telefone != new_tel:
            Fornecedor.objects.filter(pk=row.pk).update(cep=new_cep, telefone=new_tel)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("fornecedor", "0007_fornecedor_unique_cnpj_empresa"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
