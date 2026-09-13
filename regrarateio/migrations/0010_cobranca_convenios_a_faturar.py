"""Cobrança «A FATURAR» para convênios faturados (viabilidade na importação)."""

from django.db import migrations

_CONVENIO_TOKENS = (
    'fusex isent',
    'fusex pass',
    'corpo de bombeiro',
    'policia militar',
    'postal saude',
    'posta saude',
    'bradesco',
    'funcional',
    'geap',
    'cassi',
    'fusex',
)


def _norm(s: str) -> str:
    s = (s or '').strip().lower()
    for old, new in (
        ('á', 'a'), ('à', 'a'), ('ã', 'a'), ('â', 'a'),
        ('é', 'e'), ('ê', 'e'), ('í', 'i'),
        ('ó', 'o'), ('ô', 'o'), ('õ', 'o'), ('ú', 'u'), ('ç', 'c'),
    ):
        s = s.replace(old, new)
    return s


def _convenio_a_faturar(viabilidade: str) -> bool:
    t = _norm(viabilidade)
    if not t:
        return False
    return any(tok in t for tok in _CONVENIO_TOKENS)


def preencher_cobranca_convenios(apps, schema_editor):
    Cobranca = apps.get_model('cobranca', 'Cobranca')
    ContaAReceber = apps.get_model('contasareceber', 'ContaAReceber')
    LancamentoRateio = apps.get_model('regrarateio', 'LancamentoRateio')

    cob = Cobranca.objects.filter(descricao__iexact='A FATURAR').first()
    if not cob:
        return

    car_ids: set[int] = set()
    for lr in LancamentoRateio.objects.filter(
        origem='IMPORTACAO',
        conta_receber_id__isnull=False,
    ).exclude(viabilidade='').iterator():
        if _convenio_a_faturar(lr.viabilidade):
            car_ids.add(lr.conta_receber_id)

    if not car_ids:
        return

    ContaAReceber.objects.filter(
        pk__in=car_ids,
    ).exclude(forma_pagamento_id=cob.pk).update(forma_pagamento_id=cob.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0009_cobranca_a_faturar_importacao'),
        ('contasareceber', '0015_contaareceber_conta_azul_parcela_id'),
        ('cobranca', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(preencher_cobranca_convenios, migrations.RunPython.noop),
    ]
