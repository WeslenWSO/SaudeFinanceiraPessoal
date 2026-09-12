"""Totalizadores por Obs. forma nos lançamentos de rateio."""
from collections import defaultdict
from decimal import Decimal

MESES_PT = (
    '',
    'Janeiro',
    'Fevereiro',
    'Março',
    'Abril',
    'Maio',
    'Junho',
    'Julho',
    'Agosto',
    'Setembro',
    'Outubro',
    'Novembro',
    'Dezembro',
)


def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal('0')
    return x if isinstance(x, Decimal) else Decimal(str(x))


def coletar_totais_obs_forma(qs) -> dict:
    por_obs: dict[str, dict] = defaultdict(lambda: {'valor': Decimal('0'), 'qtd': 0})
    celulas = []

    for lr in qs.select_related('conta_receber', 'conta_receber__forma_pagamento'):
        obs = lr.obs_forma_exibicao()
        if obs == '—':
            obs = '(sem obs. forma)'
        valor = _to_dec(lr.valor)
        por_obs[obs]['valor'] += valor
        por_obs[obs]['qtd'] += 1

        if lr.data_pagamento:
            mes_key = lr.data_pagamento.strftime('%Y-%m')
            mes_label = f'{MESES_PT[lr.data_pagamento.month]}/{lr.data_pagamento.year}'
            celulas.append({
                'mes': mes_key,
                'mes_label': mes_label,
                'obs_forma': obs,
                'valor': str(valor.quantize(Decimal('0.01'))),
            })

    linhas = sorted(
        [
            {
                'obs_forma': nome,
                'valor': dados['valor'],
                'qtd': dados['qtd'],
            }
            for nome, dados in por_obs.items()
        ],
        key=lambda x: (-abs(x['valor']), x['obs_forma'].lower()),
    )

    return {
        'por_obs_forma': linhas,
        'celulas': celulas,
    }
