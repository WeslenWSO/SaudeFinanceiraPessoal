"""Unifica extratos POSTAL 07/2026 em 2 lotes e migra protocolo -> senha."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from faturamento_medico.models import ExtratoPagamentoConvenio, FaturamentoMedico, Lote

EMPRESA_ID = 16
LOTE_INTERNO_PRINCIPAL = 37
LOTE_INTERNO_SECUNDARIO = 46
LOTE_CONV_PRINCIPAL = '1678333'
LOTE_CONV_SECUNDARIO = '1678352'


@transaction.atomic
def run():
    # 1) protocolo (guia_lancada) -> senha; limpar protocolo
    fats_postal = FaturamentoMedico.objects.filter(
        empresa_id=EMPRESA_ID,
        convenio__icontains='POSTAL',
        data__year=2026,
        data__month=7,
    )
    migrados = 0
    for fat in fats_postal:
        prot = (fat.guia_lancada or '').strip()
        if not prot:
            continue
        update_fields = []
        if not (fat.senha or '').strip():
            fat.senha = prot[:50]
            update_fields.append('senha')
        fat.guia_lancada = ''
        update_fields.append('guia_lancada')
        fat.save(update_fields=update_fields)
        migrados += 1
    print('Faturamentos migrados protocolo->senha:', migrados)

    # 2) Unificar lotes internos 38-45 no 37
    for lid in range(38, 46):
        n = FaturamentoMedico.objects.filter(empresa_id=EMPRESA_ID, lote=str(lid)).update(
            lote=str(LOTE_INTERNO_PRINCIPAL),
        )
        if n:
            print(f'Guias movidas do lote interno #{lid} -> #{LOTE_INTERNO_PRINCIPAL}:', n)

    # 3) Remover extratos/lotes internos extras
    ExtratoPagamentoConvenio.objects.filter(
        lote_faturamento_id__in=list(range(38, 46)),
    ).delete()
    removidos = Lote.objects.filter(id__in=list(range(38, 46)), empresa_id=EMPRESA_ID).delete()
    print('Lotes internos removidos (38-45):', removidos[0])

    # 4) Ressincronizar 2 extratos com protocolo vazio
    lote_a = Lote.objects.get(pk=LOTE_INTERNO_PRINCIPAL, empresa_id=EMPRESA_ID)
    lote_b = Lote.objects.get(pk=LOTE_INTERNO_SECUNDARIO, empresa_id=EMPRESA_ID)
    lote_a.atualizar_total()
    lote_b.atualizar_total()
    ext_a = lote_a.sincronizar_extrato_pagamento(
        lote_convenio=LOTE_CONV_PRINCIPAL,
        protocolo='',
    )
    ext_b = lote_b.sincronizar_extrato_pagamento(
        lote_convenio=LOTE_CONV_SECUNDARIO,
        protocolo='',
    )

    print('--- Resultado ---')
    for ext in (ext_a, ext_b):
        print(
            f'Extrato #{ext.id} lote_conv={ext.lote} protocolo={ext.protocolo!r} '
            f'qt_guias={ext.qt_guias} valor={ext.valor}'
        )

    total = ExtratoPagamentoConvenio.objects.filter(
        empresa_id=EMPRESA_ID,
        convenio__icontains='POSTAL',
        competencia='07/2026',
    ).aggregate(t=Sum('valor'))['t']
    qtd = ExtratoPagamentoConvenio.objects.filter(
        empresa_id=EMPRESA_ID,
        convenio__icontains='POSTAL',
        competencia='07/2026',
    ).count()
    print('Extratos POSTAL 07/2026:', qtd, 'Total:', total)


if __name__ == '__main__':
    run()
