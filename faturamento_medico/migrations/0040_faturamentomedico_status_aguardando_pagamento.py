from django.db import migrations, models


def status_enviado_para_aguardando_pagamento(apps, schema_editor):
    FaturamentoMedico = apps.get_model('faturamento_medico', 'FaturamentoMedico')
    qs = FaturamentoMedico.objects.exclude(lote__isnull=True).exclude(lote='')
    qs.filter(status='enviado').update(status='aguardando_pagamento')
    qs.filter(status='pendente').update(status='aguardando_pagamento')


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0039_faturamentomedico_senha'),
    ]

    operations = [
        migrations.AlterField(
            model_name='faturamentomedico',
            name='status',
            field=models.CharField(
                choices=[
                    ('pendente', 'Pendente'),
                    ('aguardando_pagamento', 'Aguardando pagamento'),
                    ('enviado', 'Enviado'),
                    ('finalizado', 'Finalizado'),
                ],
                default='pendente',
                max_length=25,
                verbose_name='Status',
            ),
        ),
        migrations.RunPython(status_enviado_para_aguardando_pagamento, migrations.RunPython.noop),
    ]
