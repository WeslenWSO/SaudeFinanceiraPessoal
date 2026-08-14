from django.db import migrations


def seed_indicadores(apps, schema_editor):
    Empresa = apps.get_model('empresa', 'Empresa')
    Indicador = apps.get_model('indicadores', 'Indicador')
    padrao = {
        'MUSCULACAO': [
            'NPS GERAL',
            'NPS MUSCULAÇÃO',
            'NPS POR HORA',
            'MONTAGEM DE TREINO',
            'CHURN',
        ],
        'ATENDENTE': [
            'NPS geral',
            'NPS recepção',
            'NPS por horario',
            'Conversão',
            'Vendas',
            'Redução inadimplentes',
        ],
    }
    for empresa in Empresa.objects.all().iterator():
        for area, nomes in padrao.items():
            for ordem, nome in enumerate(nomes, start=1):
                Indicador.objects.get_or_create(
                    empresa_id=empresa.id,
                    area=area,
                    nome=nome,
                    defaults={'ordem': ordem, 'ativo': True},
                )


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_indicadores, migrations.RunPython.noop),
    ]
