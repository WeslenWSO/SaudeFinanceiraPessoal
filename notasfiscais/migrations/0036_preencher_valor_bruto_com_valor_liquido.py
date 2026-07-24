# Migration para preencher valor_bruto com valor_liquido onde valor_bruto está zerado

from decimal import Decimal
from django.db import migrations


def preencher_valor_bruto(apps, schema_editor):
    NotaFiscalServico = apps.get_model('notasfiscais', 'NotaFiscalServico')
    zero = Decimal('0')
    atualizadas = 0
    for nota in NotaFiscalServico.objects.filter(valor_bruto__lte=zero).exclude(valor_liquido__lte=zero):
        nota.valor_bruto = nota.valor_liquido
        nota.save(update_fields=['valor_bruto'])
        atualizadas += 1
    if atualizadas:
        print(f"[notasfiscais] Atualizadas {atualizadas} nota(s) com valor_bruto zerado (usando valor_liquido).")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('notasfiscais', '0035_alter_lognotafiscal_options_and_more'),
    ]

    operations = [
        migrations.RunPython(preencher_valor_bruto, noop),
    ]
