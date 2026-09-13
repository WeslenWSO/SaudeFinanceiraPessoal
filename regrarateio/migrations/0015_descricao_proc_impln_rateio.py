"""Regrava descrição do rateio importado: Proc:|ImpLn: (sem Pac, Mod, Viab)."""

from django.db import migrations


def _meta(observacao: str) -> dict[str, str]:
    out = {'procedimento': '', 'imp_ln': ''}
    if not observacao:
        return out
    for part in observacao.split('|'):
        p = part.strip()
        if p.startswith('Proc:'):
            out['procedimento'] = p[5:].strip()
        elif p.startswith('ImpLn:') or p.startswith('ImplLn:'):
            out['imp_ln'] = p.split(':', 1)[1].strip()
    return out


def _descricao(observacao: str) -> str:
    meta = _meta(observacao)
    parts = []
    if meta['procedimento']:
        parts.append(f"Proc:{meta['procedimento']}")
    if meta['imp_ln']:
        parts.append(f"ImpLn:{meta['imp_ln']}")
    return '|'.join(parts)


def regravar_descricoes(apps, schema_editor):
    LancamentoRateio = apps.get_model('regrarateio', 'LancamentoRateio')
    ContaAReceber = apps.get_model('contasareceber', 'ContaAReceber')
    qs = LancamentoRateio.objects.filter(conta_receber_id__isnull=False)
    for lr in qs.iterator(chunk_size=500):
        try:
            car = ContaAReceber.objects.get(pk=lr.conta_receber_id)
        except ContaAReceber.DoesNotExist:
            continue
        obs = (car.observacao or '').strip()
        if not obs or 'Pac:' not in obs:
            continue
        nova = _descricao(obs)[:255]
        if nova and nova != lr.descricao:
            lr.descricao = nova
            lr.save(update_fields=['descricao'])


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0014_origem_total_receita_usg'),
    ]

    operations = [
        migrations.RunPython(regravar_descricoes, migrations.RunPython.noop),
    ]
