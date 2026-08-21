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


def _convenio_na_lista_sem_nf(chave: str) -> bool:
    """True se o convênio normalizado corresponde a algum da lista (nome completo ou prefixo)."""
    for excluido in CONVENIOS_SEM_NF_PAGAMENTO:
        if chave == excluido or chave.startswith(excluido + ' '):
            return True
    return False


def convenio_mostra_nf_pagamento(convenio: str | None) -> bool:
    """True para convênios que devem exibir NF / forma de pagamento (fora da lista pública)."""
    chave = _normalizar_convenio(convenio or '')
    if not chave:
        return True
    return not _convenio_na_lista_sem_nf(chave)
