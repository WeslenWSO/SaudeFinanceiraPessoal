from decimal import Decimal

from django.db import migrations


CONVENIOS_NOVOS = (
    'CORTESIA',
    'MED PREV',
    'SILVESTRE SANTE',
)

ALIQUOTAS_PADRAO = {
    'aliquota_iss_ap': Decimal('3.00'),
    'aliquota_pis_ap': Decimal('0.65'),
    'aliquota_cofins_ap': Decimal('3.00'),
    'aliquota_csll_ap': Decimal('2.88'),
    'aliquota_irpj_ap': Decimal('4.80'),
}


def cadastrar_convenios_viabilidade(apps, schema_editor):
    Convenio = apps.get_model('servicos_medicos', 'Convenio')
    Empresa = apps.get_model('empresa', 'Empresa')

    empresa = (
        Empresa.objects.filter(pk=16).first()
        or Empresa.objects.filter(razao__icontains='MEDICINARTE').order_by('id').first()
    )
    if not empresa:
        return

    for nome in CONVENIOS_NOVOS:
        exists = Convenio.objects.filter(empresa_id=empresa.id, nome__iexact=nome).exists()
        if exists:
            continue
        Convenio.objects.create(empresa_id=empresa.id, nome=nome, **ALIQUOTAS_PADRAO)


def remover_convenios_viabilidade(apps, schema_editor):
    Convenio = apps.get_model('servicos_medicos', 'Convenio')
    Empresa = apps.get_model('empresa', 'Empresa')

    empresa = (
        Empresa.objects.filter(pk=16).first()
        or Empresa.objects.filter(razao__icontains='MEDICINARTE').order_by('id').first()
    )
    if not empresa:
        return

    for nome in CONVENIOS_NOVOS:
        Convenio.objects.filter(empresa_id=empresa.id, nome__iexact=nome).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('servicos_medicos', '0008_convenio_aliquotas_apuracao'),
        ('empresa', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(cadastrar_convenios_viabilidade, remover_convenios_viabilidade),
    ]
