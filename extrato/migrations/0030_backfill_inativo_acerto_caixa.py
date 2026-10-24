from django.db import migrations
from django.db.models import Q


def marcar_inativos_acerto(apps, schema_editor):
    ContaBancaria = apps.get_model('extrato', 'ContaBancaria')
    elegivel = Q(tipo__in=('CAIXA', 'OUTROS')) | Q(descricao__icontains='caixa')
    ContaBancaria.objects.filter(elegivel).filter(
        Q(status='I') | Q(inativo_acerto_caixa=True),
    ).update(inativo_acerto_caixa=True)


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0029_contabancaria_inativo_acerto_caixa'),
    ]

    operations = [
        migrations.RunPython(marcar_inativos_acerto, migrations.RunPython.noop),
    ]
