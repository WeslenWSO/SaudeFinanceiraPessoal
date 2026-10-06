"""Extração de texto de PDFs de cotação (referência manual)."""
from __future__ import annotations


def extrair_texto_pdf(arquivo) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ''
    partes: list[str] = []
    try:
        with pdfplumber.open(arquivo) as pdf:
            for page in pdf.pages[:30]:
                txt = page.extract_text() or ''
                if txt.strip():
                    partes.append(txt.strip())
    except Exception:
        return ''
    return '\n\n'.join(partes)
