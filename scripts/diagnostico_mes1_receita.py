"""Compara totais jan/2026: planilha importada vs sistema (convênio viabilidade)."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

import django

django.setup()

from django.db.models import Sum, Count, Q

from contasareceber.models import ContaAReceber
from regrarateio.convenio_viabilidade import coletar_totais_por_viabilidade_convenio
from regrarateio.models import LancamentoRateio

EMPRESA_ID = 16
DI, DF = '2026-01-01', '2026-01-31'
PLANILHA_TOTAL = Decimal('120738.02')
SISTEMA_TOTAL = Decimal('119443.55')


def p(label, agg):
    print(f'{label}: qtd={agg.get("n") or agg.get("qtd") or 0}, total={agg.get("s") or agg.get("total") or 0}')


def main():
    print(f'=== Diagnóstico mês 1/2026 — empresa {EMPRESA_ID} ===')
    print(f'Planilha (referência): R$ {PLANILHA_TOTAL}')
    print(f'Sistema modal (referência): R$ {SISTEMA_TOTAL}')
    print(f'Diferença esperada: R$ {PLANILHA_TOTAL - SISTEMA_TOTAL}')
    print()

    car = ContaAReceber.objects.filter(
        empresa_id=EMPRESA_ID,
        observacao__contains='Pac:',
        data_emissao__gte=DI,
        data_emissao__lte=DF,
    )
    p('CAR importados (emissão jan/2026)', car.aggregate(s=Sum('valor_a_receber'), n=Count('id')))

    qs = LancamentoRateio.objects.filter(
        empresa_id=EMPRESA_ID,
        data_pagamento__gte=DI,
        data_pagamento__lte=DF,
    )
    p('LR total (data_pagamento)', qs.aggregate(s=Sum('valor'), n=Count('id')))
    qs_rec = qs.filter(tipo='RECEBIMENTO')
    p('LR RECEBIMENTO', qs_rec.aggregate(s=Sum('valor'), n=Count('id')))
    p('LR IMPORTACAO RECEBIMENTO', qs_rec.filter(origem='IMPORTACAO').aggregate(s=Sum('valor'), n=Count('id')))
    p('LR RECEBIMENTO não-importação', qs_rec.exclude(origem='IMPORTACAO').aggregate(s=Sum('valor'), n=Count('id')))
    p('LR PGTO', qs.filter(tipo='PGTO').aggregate(s=Sum('valor'), n=Count('id')))

    tot = coletar_totais_por_viabilidade_convenio(EMPRESA_ID, qs)
    print(f'\nModal convênio total_geral: R$ {tot["total_geral"]}')
    soma_outros = sum(o['total'] for o in tot['outros'])
    print(f'Soma "outros" (viab. sem convênio): R$ {soma_outros}')
    for o in tot['outros']:
        print(f'  - {o["viabilidade"]}: qtd={o["qtd"]}, total={o["total"]}')

    vaz = qs.filter(Q(viabilidade='') | Q(viabilidade__isnull=True))
    p('\nViabilidade vazia (fora do modal)', vaz.aggregate(s=Sum('valor'), n=Count('id')))

    # CAR em jan cujo LR cai fora de jan
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT car.id), COALESCE(SUM(car.valor_a_receber), 0)
            FROM contasareceber_contaareceber car
            JOIN regrarateio_lancamentorateio lr ON lr.conta_receber_id = car.id
            WHERE car.empresa_id = %s
              AND car.observacao LIKE '%%Pac:%%'
              AND car.data_emissao >= %s AND car.data_emissao <= %s
              AND (lr.data_pagamento < %s OR lr.data_pagamento > %s)
            """,
            [EMPRESA_ID, DI, DF, DI, DF],
        )
        row = cur.fetchone()
        print(f'\nCAR importados jan com LR fora de jan: qtd={row[0]}, total CAR={row[1]}')

        cur.execute(
            """
            SELECT car.id, car.valor_a_receber, SUM(lr.valor) AS soma_lr
            FROM contasareceber_contaareceber car
            JOIN regrarateio_lancamentorateio lr ON lr.conta_receber_id = car.id
            WHERE car.empresa_id = %s
              AND car.observacao LIKE '%%Pac:%%'
              AND car.data_emissao >= %s AND car.data_emissao <= %s
            GROUP BY car.id, car.valor_a_receber
            HAVING ABS(car.valor_a_receber - SUM(lr.valor)) > 0.05
            """,
            [EMPRESA_ID, DI, DF],
        )
        drift = cur.fetchall()
        if drift:
            print(f'\nDrift CAR vs soma LR: {len(drift)} títulos')
            for d in drift[:20]:
                print(f'  CAR#{d[0]} valor={d[1]} soma_lr={d[2]} diff={Decimal(d[1]) - Decimal(d[2])}')
        else:
            print('\nSem drift CAR vs soma LR (> R$ 0,05)')

    # Só RECEBIMENTO importação por emissão do CAR
    lr_imp_jan_emissao = LancamentoRateio.objects.filter(
        empresa_id=EMPRESA_ID,
        origem='IMPORTACAO',
        tipo='RECEBIMENTO',
        conta_receber__observacao__contains='Pac:',
        conta_receber__data_emissao__gte=DI,
        conta_receber__data_emissao__lte=DF,
    )
    p('\nLR importação (CAR emissão jan, qualquer data_pagamento)', lr_imp_jan_emissao.aggregate(s=Sum('valor'), n=Count('id')))

    # Viabilidades no LR jan que não batem convênio - detalhe
    print('\n--- Detalhe viabilidades "outros" ---')
    if not tot['outros']:
        print('(nenhuma)')


if __name__ == '__main__':
    main()
