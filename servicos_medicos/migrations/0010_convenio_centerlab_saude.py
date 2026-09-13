from decimal import Decimal

from django.db import migrations

CONVENIO_NOME = 'CENTERLAB SAUDE'

ALIQUOTAS_PADRAO = {
    'aliquota_iss_ap': Decimal('3.00'),
    'aliquota_pis_ap': Decimal('0.65'),
    'aliquota_cofins_ap': Decimal('3.00'),
    'aliquota_csll_ap': Decimal('2.88'),
    'aliquota_irpj_ap': Decimal('4.80'),
}


def cadastrar_centerlab(apps, schema_editor):
    Convenio = apps.get_model('servicos_medicos', 'Convenio')
    Empresa = apps.get_model('empresa', 'Empresa')

    empresa = (
        Empresa.objects.filter(pk=16).first()
        or Empresa.objects.filter(nome__icontains='MEDICINARTE').order_by('id').first()
    )
    if not empresa:
        return

    exists = Convenio.objects.filter(empresa_id=empresa.id, nome__iexact=CONVENIO_NOME).exists()
    if exists:
        return

    Convenio.objects.create(empresa_id=empresa.id, nome=CONVENIO_NOME, **ALIQUOTAS_PADRAO)


def remover_centerlab(apps, schema_editor):
    Convenio = apps.get_model('servicos_medicos', 'Convenio')
    Empresa = apps.get_model('empresa', 'Empresa')

    empresa = (
        Empresa.objects.filter(pk=16).first()
        or Empresa.objects.filter(nome__icontains='MEDICINARTE').order_by('id').first()
    )
    if not empresa:
        return

    Convenio.objects.filter(empresa_id=empresa.id, nome__iexact=CONVENIO_NOME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('servicos_medicos', '0009_convenios_cortesia_medprev_silvestre'),
        ('empresa', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(cadastrar_centerlab, remover_centerlab),
    ]
