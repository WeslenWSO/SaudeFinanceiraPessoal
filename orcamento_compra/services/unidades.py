"""Unidades para itens do orçamento de compra."""
from __future__ import annotations

from notafiscalentrada.models import NotaFiscalEntradaItem

# Comuns em compras / NF (inclui exemplos citados pelo usuário)
UNIDADES_PADRAO: tuple[str, ...] = (
    'UN',
    'UN1',
    'UNID',
    'PCT',
    'PC',
    'CX',
    'CAIXA',
    'CAIXA-UNIDADE',
    'FRASCO-SC',
    'FR',
    'FRASCO',
    'AMP',
    'ML',
    'LT',
    'L',
    'KG',
    'G',
    'M',
    'M2',
    'M3',
    'PAR',
    'KIT',
    'RL',
    'TB',
    'BG',
    'SC',
)


def listar_unidades_disponiveis(empresa_id: int) -> list[str]:
    """Unidades padrão + distintas das NF de comércio da empresa (sem duplicar ignorando maiúsculas)."""
    vistos: dict[str, str] = {}
    for u in UNIDADES_PADRAO:
        chave = u.lower()
        if chave not in vistos:
            vistos[chave] = u

    qs = (
        NotaFiscalEntradaItem.objects.filter(
            nota_fiscal__empresa_id=empresa_id,
            nota_fiscal__tipo_nota='comercio',
        )
        .exclude(unidade='')
        .values_list('unidade', flat=True)
        .distinct()
    )
    for u in qs:
        texto = (u or '').strip()
        if not texto:
            continue
        chave = texto.lower()
        if chave not in vistos:
            vistos[chave] = texto

    return sorted(vistos.values(), key=lambda x: x.lower())


def normalizar_unidade_escolhida(valor: str, unidades: list[str]) -> str:
    valor = (valor or '').strip()
    if not valor:
        return 'UN'
    for u in unidades:
        if u.lower() == valor.lower():
            return u
    return valor[:20]
