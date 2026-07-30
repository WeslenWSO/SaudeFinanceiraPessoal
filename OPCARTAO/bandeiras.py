"""Ícones e cores das bandeiras de cartão (Font Awesome brands)."""
from __future__ import annotations

import unicodedata


BANDEIRA_ICONES = {
    'VISA': {'icone': 'fa-cc-visa', 'cor': '#1a1f71', 'nome': 'Visa'},
    'MASTERCARD': {'icone': 'fa-cc-mastercard', 'cor': '#eb001b', 'nome': 'Mastercard'},
    'ELO': {'icone': 'fa-credit-card', 'cor': '#00a4e0', 'nome': 'Elo'},
    'AMEX': {'icone': 'fa-cc-amex', 'cor': '#006fcf', 'nome': 'American Express'},
    'HIPERCARD': {'icone': 'fa-credit-card', 'cor': '#822124', 'nome': 'Hipercard'},
    'OUTRA': {'icone': 'fa-credit-card', 'cor': '#6c757d', 'nome': 'Cartão'},
}


def _normalizar(txt: str) -> str:
    if not txt:
        return ''
    d = unicodedata.normalize('NFKD', txt)
    s = ''.join(c for c in d if unicodedata.category(c) != 'Mn').upper()
    return s.strip()


def resolver_bandeira(*fontes: str | None) -> dict[str, str]:
    for fonte in fontes:
        if not fonte:
            continue
        chave = _normalizar(fonte)
        if chave in BANDEIRA_ICONES:
            return BANDEIRA_ICONES[chave]
        for codigo, info in BANDEIRA_ICONES.items():
            if codigo in chave or info['nome'].upper() in chave:
                return info
        if 'VISA' in chave:
            return BANDEIRA_ICONES['VISA']
        if 'MASTER' in chave:
            return BANDEIRA_ICONES['MASTERCARD']
        if 'AMEX' in chave or 'AMERICAN' in chave:
            return BANDEIRA_ICONES['AMEX']
        if 'ELO' in chave:
            return BANDEIRA_ICONES['ELO']
        if 'HIPER' in chave:
            return BANDEIRA_ICONES['HIPERCARD']
    return BANDEIRA_ICONES['OUTRA']
