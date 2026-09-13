"""Totalizadores por Cobrança nos lançamentos de rateio."""
from collections import defaultdict
from decimal import Decimal

from regrarateio.obs_forma_totalizadores import MESES_PT, _to_dec


def coletar_totais_cobranca(qs) -> dict:
    por_cob: dict[str, dict] = defaultdict(lambda: {'valor': Decimal('0'), 'qtd': 0})
    celulas = []

    for lr in qs.select_related(
        'conta_receber',
        'conta_receber__forma_pagamento',
        'conta_pagar',
        'conta_pagar__cobranca',
    ):
        cob = lr.cobranca_exibicao()
        if cob == '—':
            cob = '(sem cobrança)'
        valor = _to_dec(lr.valor)
        por_cob[cob]['valor'] += valor
        por_cob[cob]['qtd'] += 1

        if lr.data_pagamento:
            mes_key = lr.data_pagamento.strftime('%Y-%m')
            mes_label = f'{MESES_PT[lr.data_pagamento.month]}/{lr.data_pagamento.year}'
            celulas.append({
                'mes': mes_key,
                'mes_label': mes_label,
                'cobranca': cob,
                'valor': str(valor.quantize(Decimal('0.01'))),
            })

    linhas = sorted(
        [
            {
                'cobranca': nome,
                'valor': dados['valor'],
                'qtd': dados['qtd'],
            }
            for nome, dados in por_cob.items()
        ],
        key=lambda x: (-abs(x['valor']), x['cobranca'].lower()),
    )

    return {
        'por_cobranca': linhas,
        'celulas': celulas,
    }
