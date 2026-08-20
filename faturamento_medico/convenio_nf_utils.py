"""Convênios que não exibem coluna NF / forma de pagamento na listagem."""

from __future__ import annotations

import unicodedata

CONVENIOS_SEM_NF_PAGAMENTO = frozenset({
    'BRADESCO',
    'CASSI',
    'CORPO DE BOMBEIRO',
    'FUNCIONAL HEALTH',
    'FUSEX',
    'FUSEX ISENTO',
    'FUSEX PASS',
    'GEAP',
    'POLICIA MILITAR',
    'POSTAL SAUDE',
    'PP SAUDE',
})


def _normalizar_convenio(nome: str) -> str:
    n = (nome or '').strip().upper()
    n = unicodedata.normalize('NFD', n)
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
    return ' '.join(n.split())


def convenio_mostra_nf_pagamento(convenio: str | None) -> bool:
    """True para convênios que devem exibir NF / forma de pagamento (fora da lista pública)."""
    chave = _normalizar_convenio(convenio or '')
    if not chave:
        return True
    return chave not in CONVENIOS_SEM_NF_PAGAMENTO
