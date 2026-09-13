"""Preenche forma_pagamento «A FATURAR» em recebimentos importados."""

from django.db import migrations


def preencher_cobranca_a_faturar(apps, schema_editor):
    Cobranca = apps.get_model('cobranca', 'Cobranca')
    ContaAReceber = apps.get_model('contasareceber', 'ContaAReceber')
    LancamentoRateio = apps.get_model('regrarateio', 'LancamentoRateio')

    cob = Cobranca.objects.filter(descricao__iexact='A FATURAR').first()
    if not cob:
        return

    cars = ContaAReceber.objects.filter(
        forma_pagamento__isnull=True,
        observacao__contains='Pac:',
        doc__icontains='FATURAR',
    )
    car_ids = list(cars.values_list('pk', flat=True))
    if not car_ids:
        return

    cars.update(forma_pagamento_id=cob.pk)
    LancamentoRateio.objects.filter(
        conta_receber_id__in=car_ids,
        origem='IMPORTACAO',
    ).filter(obs_forma='').update(obs_forma='A FATURAR')


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0008_limpar_obs_rateio_recebimento_importado'),
        ('contasareceber', '0015_contaareceber_conta_azul_parcela_id'),
        ('cobranca', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(preencher_cobranca_a_faturar, migrations.RunPython.noop),
    ]
