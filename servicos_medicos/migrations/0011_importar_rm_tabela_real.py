"""Vincula exames de RM na TABELA - REAL (REAL CONVÊNIOS) se ainda não importados."""
from __future__ import annotations

from django.core.management import call_command
from django.db import migrations


def _rm_ja_importada_real() -> bool:
    from servicos_medicos.models import Cabecalho, TabelaPreco

    cab = (
        Cabecalho.objects.filter(nome_tabela__icontains="REAL")
        .order_by("id")
        .first()
    )
    if not cab:
        return False
    return (
        TabelaPreco.objects.filter(
            cabecalho=cab,
            codigo_servico__codigo__startswith="411",
        ).count()
        >= 30
    )


def importar_rm_tabela_real(apps, schema_editor):
    if _rm_ja_importada_real():
        return
    call_command("importar_tabela_real", "rm", verbosity=1)


class Migration(migrations.Migration):
    dependencies = [
        ("servicos_medicos", "0010_convenio_centerlab_saude"),
    ]

    operations = [
        migrations.RunPython(importar_rm_tabela_real, migrations.RunPython.noop),
    ]
