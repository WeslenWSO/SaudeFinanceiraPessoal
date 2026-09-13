"""Corrige campo cliente nos CAR importados (jan–set/2026): nome do paciente em vez de viabilidade."""

from django.db import migrations


def _meta_observacao(observacao: str) -> dict[str, str]:
    out = {'paciente': '', 'viabilidade': ''}
    if not observacao:
        return out
    for part in observacao.split('|'):
        p = part.strip()
        if p.startswith('Pac:'):
            out['paciente'] = p[4:].strip()
        elif p.startswith('Viab:'):
            out['viabilidade'] = p[5:].strip()
    return out


def corrigir_cliente_paciente(apps, schema_editor):
    ContaAReceber = apps.get_model('contasareceber', 'ContaAReceber')
    qs = ContaAReceber.objects.filter(
        observacao__contains='Pac:',
        data_emissao__year=2026,
        data_emissao__month__gte=1,
        data_emissao__month__lte=9,
    )
    for car in qs.iterator(chunk_size=500):
        meta = _meta_observacao(car.observacao or '')
        paciente = meta['paciente']
        if not paciente:
            continue
        if car.cliente == paciente:
            continue
        car.cliente = paciente[:200]
        car.save(update_fields=['cliente'])


class Migration(migrations.Migration):

    dependencies = [
        ('contasareceber', '0015_contaareceber_conta_azul_parcela_id'),
    ]

    operations = [
        migrations.RunPython(corrigir_cliente_paciente, migrations.RunPython.noop),
    ]
