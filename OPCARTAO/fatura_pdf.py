"""Detecção e importação unificada de faturas de cartão (PDF)."""
from __future__ import annotations

from typing import Any

from .sicredi_pdf import parse_fatura_sicredi_pdf
from .sicoob_pdf import parse_fatura_sicoob_pdf


def detectar_banco_fatura_pdf(arquivo) -> str:
    pos = arquivo.tell()
    try:
        from .sicredi_pdf import pdfplumber
        if pdfplumber is None:
            return 'DESCONHECIDO'
        with pdfplumber.open(arquivo) as pdf:
            texto = '\n'.join(page.extract_text() or '' for page in pdf.pages[:2]).upper()
    finally:
        arquivo.seek(pos)

    if 'SICOOB' in texto and 'EXTRATO DE CART' in texto:
        return 'SICOOB'
    if 'SICREDI' in texto or 'TOTAL FATURA DE' in texto or 'VISA EMPRESAS FINAL' in texto:
        return 'SICREDI'
    if 'GASTOS DE ' in texto and 'TOTAL DA FATURA' in texto:
        return 'SICOOB'
    return 'DESCONHECIDO'


def parse_fatura_cartao_pdf(arquivo) -> dict[str, Any]:
    banco = detectar_banco_fatura_pdf(arquivo)
    if banco == 'SICOOB':
        return parse_fatura_sicoob_pdf(arquivo)
    if banco == 'SICREDI':
        return parse_fatura_sicredi_pdf(arquivo)
    raise ValueError(
        'Não foi possível identificar o banco da fatura. '
        'Formatos suportados: Sicredi e Sicoob (PDF).'
    )
