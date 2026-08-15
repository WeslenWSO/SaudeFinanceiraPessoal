from django.db import migrations


def finalizar_faturamentos_extratos_baixados(apps, schema_editor):
    ExtratoPagamentoConvenio = apps.get_model('faturamento_medico', 'ExtratoPagamentoConvenio')
    FaturamentoMedico = apps.get_model('faturamento_medico', 'FaturamentoMedico')

    for extrato in ExtratoPagamentoConvenio.objects.filter(lote_faturamento__isnull=False):
        if not extrato.data_recebimento or not (extrato.valor_recebido or 0):
            continue
        lote_id = str(extrato.lote_faturamento_id)
        qs = FaturamentoMedico.objects.filter(
            empresa_id=extrato.empresa_id,
            lote=lote_id,
            status__in=['aguardando_pagamento', 'enviado', 'pendente'],
        )
        qs.update(status='finalizado', data_fechamento=extrato.data_recebimento)


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0040_faturamentomedico_status_aguardando_pagamento'),
    ]

    operations = [
        migrations.RunPython(finalizar_faturamentos_extratos_baixados, migrations.RunPython.noop),
    ]
