from django.db import migrations, models


def popular_status_recebimento(apps, schema_editor):
    Extrato = apps.get_model('faturamento_medico', 'ExtratoPagamentoConvenio')
    for extrato in Extrato.objects.all():
        if extrato.data_recebimento and (extrato.valor_recebido or 0) > 0:
            status = 'finalizado'
        elif (extrato.nota or '').strip():
            status = 'pendente_com_nota'
        else:
            status = 'pendente'
        Extrato.objects.filter(pk=extrato.pk).update(status_recebimento=status)


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0046_lancamento_anestesista_pago'),
    ]

    operations = [
        migrations.AddField(
            model_name='extratopagamentoconvenio',
            name='status_recebimento',
            field=models.CharField(
                choices=[
                    ('pendente', 'Pendente'),
                    ('pendente_com_nota', 'Pendente com Nota'),
                    ('finalizado', 'Finalizado'),
                ],
                default='pendente',
                max_length=20,
                verbose_name='Status recebimento',
            ),
        ),
        migrations.RunPython(popular_status_recebimento, migrations.RunPython.noop),
    ]
