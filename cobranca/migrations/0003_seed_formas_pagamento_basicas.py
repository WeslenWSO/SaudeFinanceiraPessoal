# Migration de dados: cria formas básicas de pagamento em Cobranca se não existirem.
# Permite que a importação de NFSe vincule forma_pagamento (PIX, DINHEIRO, CC, CD).
# Seguro para produção: não duplica registros.

from django.db import migrations


def seed_formas_basicas(apps, schema_editor):
    Cobranca = apps.get_model("cobranca", "Cobranca")
    # formapgto='0' (A Vista), intervaloparcelas=0; tpag conforme NF-e
    formas = [
        {"descricao": "PIX", "tpag": "PIX"},
        {"descricao": "DINHEIRO", "tpag": "DH"},
        {"descricao": "CARTAO CREDITO", "tpag": "CC"},
        {"descricao": "CARTAO DEBITO", "tpag": "CD"},
    ]
    for f in formas:
        if not Cobranca.objects.filter(descricao__iexact=f["descricao"]).exists():
            Cobranca.objects.create(
                formapgto="0",
                descricao=f["descricao"],
                tpag=f["tpag"],
                intervaloparcelas=0,
            )


def reverse_seed(apps, schema_editor):
    # Opcional: não remove registros para evitar quebrar FKs em NotaFiscalServico
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cobranca", "0002_cobranca_intervaloparcelas"),
    ]

    operations = [
        migrations.RunPython(seed_formas_basicas, reverse_seed),
    ]
