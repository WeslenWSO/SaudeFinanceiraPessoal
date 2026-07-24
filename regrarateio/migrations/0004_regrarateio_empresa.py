# Generated manually: regra de rateio por empresa

from django.db import migrations, models
import django.db.models.deletion


def forwards_assign_empresa(apps, schema_editor):
    RegraRateio = apps.get_model('regrarateio', 'RegraRateio')
    RegraRateioItem = apps.get_model('regrarateio', 'RegraRateioItem')
    Socio = apps.get_model('socio', 'Socio')
    Empresa = apps.get_model('empresa', 'Empresa')
    first_emp = Empresa.objects.order_by('id').first()
    if not first_emp:
        raise ValueError(
            'Migração requer ao menos uma empresa cadastrada. Cadastre uma empresa e rode migrate de novo.'
        )
    for regra in RegraRateio.objects.filter(empresa__isnull=True):
        eid = None
        item = RegraRateioItem.objects.filter(regrarateio=regra).first()
        if item and item.socios_id:
            socio = Socio.objects.filter(pk=item.socios_id).first()
            if socio and getattr(socio, 'empresa_id', None):
                eid = socio.empresa_id
        regra.empresa_id = eid or first_emp.pk
        regra.save(update_fields=['empresa_id'])


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0012_socio'),
        ('regrarateio', '0003_regrarateio_codigo_alter_regrarateio_nomedaregra_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='regrarateio',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='regras_rateio',
                to='empresa.empresa',
                verbose_name='Empresa',
            ),
        ),
        migrations.RunPython(forwards_assign_empresa, backwards_noop),
        migrations.AlterField(
            model_name='regrarateio',
            name='empresa',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='regras_rateio',
                to='empresa.empresa',
                verbose_name='Empresa',
            ),
        ),
    ]
