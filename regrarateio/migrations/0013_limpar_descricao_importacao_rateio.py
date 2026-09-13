"""Remove Pac, Mod e Viab da descrição dos lançamentos importados."""

from django.db import migrations


def _limpar(texto: str) -> str:
    t = (texto or '').strip()
    if not t:
        return ''
    if 'Pac:' not in t and 'Mod:' not in t and 'Viab:' not in t:
        return t
    parts = []
    for part in t.split('|'):
        p = part.strip()
        if not p:
            continue
        if p.startswith('Pac:') or p.startswith('Mod:') or p.startswith('Viab:'):
            continue
        parts.append(p)
    return '|'.join(parts)


def limpar_descricoes(apps, schema_editor):
    LancamentoRateio = apps.get_model('regrarateio', 'LancamentoRateio')
    qs = LancamentoRateio.objects.filter(descricao__contains='Pac:')
    for lr in qs.iterator(chunk_size=500):
        nova = _limpar(lr.descricao)[:255]
        if nova != lr.descricao:
            lr.descricao = nova
            lr.save(update_fields=['descricao'])


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0012_lancamento_tipo_deducao_receita'),
    ]

    operations = [
        migrations.RunPython(limpar_descricoes, migrations.RunPython.noop),
    ]
