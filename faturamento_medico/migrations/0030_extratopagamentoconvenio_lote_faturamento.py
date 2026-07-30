from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0029_extratopagamentoconvenio'),
    ]

    operations = [
        migrations.AddField(
            model_name='extratopagamentoconvenio',
            name='lote_faturamento',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='linhas_extrato_pagamento',
                to='faturamento_medico.lote',
                verbose_name='Lote de faturamento',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='extratopagamentoconvenio',
            name='uniq_extrato_pagamento_convenio',
        ),
        migrations.AddConstraint(
            model_name='extratopagamentoconvenio',
            constraint=models.UniqueConstraint(
                condition=models.Q(('lote_faturamento__isnull', False)),
                fields=('lote_faturamento',),
                name='uniq_extrato_por_lote_faturamento',
            ),
        ),
        migrations.AddConstraint(
            model_name='extratopagamentoconvenio',
            constraint=models.UniqueConstraint(
                condition=models.Q(('lote_faturamento__isnull', True)),
                fields=(
                    'empresa', 'competencia', 'protocolo', 'lote',
                    'data_recebimento', 'valor', 'valor_liberado',
                ),
                name='uniq_extrato_pagamento_convenio',
            ),
        ),
    ]
