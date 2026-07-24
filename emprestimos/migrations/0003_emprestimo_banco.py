# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def preencher_banco_sicoob(apps, schema_editor):
    Emprestimo = apps.get_model('emprestimos', 'Emprestimo')
    Banco = apps.get_model('extrato', 'Banco')
    banco = (
        Banco.objects.filter(codigo='756').first()
        or Banco.objects.filter(nome__iexact='SICOOB').first()
        or Banco.objects.filter(nome__icontains='sicoob').first()
    )
    if not banco:
        banco = Banco.objects.create(nome='SICOOB', codigo='756')
    Emprestimo.objects.filter(banco__isnull=True).update(banco_id=banco.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('emprestimos', '0002_indicador_calculo_sicoob'),
        ('extrato', '0008_banco_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='emprestimo',
            name='banco',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='emprestimos',
                to='extrato.banco',
                verbose_name='Banco',
            ),
        ),
        migrations.RunPython(preencher_banco_sicoob, noop_reverse),
    ]
