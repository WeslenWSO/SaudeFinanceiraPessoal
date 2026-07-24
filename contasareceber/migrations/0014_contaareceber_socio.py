# Generated manually for sync NF ↔ contas a receber (sócio)

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import OuterRef, Subquery


def copy_socio_from_nota(apps, schema_editor):
    ContaAReceber = apps.get_model('contasareceber', 'ContaAReceber')
    NotaFiscalServico = apps.get_model('notasfiscais', 'NotaFiscalServico')
    ContaAReceber.objects.filter(nota_id__isnull=False).update(
        socio_id=Subquery(
            NotaFiscalServico.objects.filter(pk=OuterRef('nota_id')).values('socio_id')[:1]
        )
    )


def noop_reverse(apps, schema_editor):
    ContaAReceber = apps.get_model('contasareceber', 'ContaAReceber')
    ContaAReceber.objects.all().update(socio_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('notasfiscais', '0039_merge_0036_0038'),
        ('socio', '0005_socio_cpf'),
        ('contasareceber', '0013_alter_contaareceber_forma_pagamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='contaareceber',
            name='socio',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='socio.socio',
                verbose_name='Sócio responsável',
            ),
        ),
        migrations.RunPython(copy_socio_from_nota, noop_reverse),
    ]
