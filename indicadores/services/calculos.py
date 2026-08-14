from decimal import Decimal


def _dec(val) -> Decimal | None:
    if val is None or val == '':
        return None
    return Decimal(str(val))


# Faixas de premiação do CHURN (planilha academia)
FAIXAS_PREMIACAO_CHURN: tuple[tuple[Decimal, Decimal, Decimal], ...] = (
    (Decimal('0'), Decimal('2.99'), Decimal('30.00')),
    (Decimal('3'), Decimal('3.99'), Decimal('20.00')),
    (Decimal('4'), Decimal('5.99'), Decimal('10.00')),
)

FAIXAS_PREMIACAO_CHURN_LABELS: tuple[tuple[str, str], ...] = (
    ('0 a 2,99%', 'R$ 30,00'),
    ('3 a 3,99%', 'R$ 20,00'),
    ('4 a 5,99%', 'R$ 10,00'),
    ('6 ou mais', 'R$ 0,00'),
)


def atingimento_pct(meta, resultado) -> Decimal | None:
    meta = _dec(meta)
    resultado = _dec(resultado)
    if meta is None or resultado is None or meta <= 0:
        return None
    pct = (resultado / meta) * Decimal('100')
    return min(pct, Decimal('100')).quantize(Decimal('0.01'))


def premiacao_churn_faixas(churn_pct: Decimal) -> Decimal:
    """
    Churn (%) = qt cancelados / qt ativos.
    Localiza a faixa e retorna o valor fixo da premiação.
    """
    churn = _dec(churn_pct) or Decimal('0')
    if churn >= Decimal('6'):
        return Decimal('0.00')
    for ini, fim, valor in FAIXAS_PREMIACAO_CHURN:
        if ini <= churn <= fim:
            return valor
    return Decimal('0.00')


def valor_premiacao(indicador, meta, resultado, churn_pct=None) -> Decimal:
    if indicador.eh_churn:
        return premiacao_churn_faixas(churn_pct or Decimal('0'))
    prem = _dec(indicador.premiacao) or Decimal('0')
    meta = _dec(meta)
    resultado = _dec(resultado)
    if meta is None or resultado is None or meta <= 0 or prem <= 0:
        return Decimal('0.00')
    ratio = min(Decimal('1'), resultado / meta)
    return (prem * ratio).quantize(Decimal('0.01'))


def montar_linha_indicador(indicador, item, churn_pct=None) -> dict:
    meta = item.meta if item else None
    resultado = item.resultado if item else None
    if indicador.eh_churn and churn_pct is not None:
        resultado = churn_pct
    ating = None if indicador.eh_churn else atingimento_pct(meta, resultado)
    valor = valor_premiacao(indicador, meta, resultado, churn_pct=churn_pct)
    return {
        'indicador': indicador,
        'item': item,
        'meta': meta,
        'resultado': resultado,
        'atingimento_pct': ating,
        'valor_premiacao': valor,
    }
