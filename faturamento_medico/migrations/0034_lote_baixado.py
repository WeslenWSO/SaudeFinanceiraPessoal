from django.db import migrations, models


def marcar_lotes_baixados_do_extrato(apps, schema_editor):
    ExtratoPagamentoConvenio = apps.get_model('faturamento_medico', 'ExtratoPagamentoConvenio')
    Lote = apps.get_model('faturamento_medico', 'Lote')

    for extrato in ExtratoPagamentoConvenio.objects.filter(lote_faturamento__isnull=False):
        if extrato.data_recebimento and (extrato.valor_recebido or 0) > 0:
            Lote.objects.filter(pk=extrato.lote_faturamento_id).update(baixado=True)


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0033_itemservico_status_falta_tabela_contraste'),
    ]

    operations = [
        migrations.AddField(
            model_name='lote',
            name='baixado',
            field=models.BooleanField(
                default=False,
                help_text='Lote recebido e baixado — não aparece na seleção de impressão.',
                verbose_name='Lote baixado',
            ),
        ),
        migrations.RunPython(marcar_lotes_baixados_do_extrato, migrations.RunPython.noop),
    ]
