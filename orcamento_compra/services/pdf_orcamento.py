"""Extração de texto de PDFs de cotação (referência manual)."""
from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def extrair_texto_pdf(arquivo) -> str:
    try:
        import pdfplumber
    except ImportError:
        logger.warning('pdfplumber não instalado; texto do PDF não será extraído.')
        return ''

    if hasattr(arquivo, 'seek'):
        arquivo.seek(0)

    if hasattr(arquivo, 'read'):
        raw = arquivo.read()
        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)
        if not raw:
            return ''
        stream = BytesIO(raw)
    else:
        stream = arquivo

    partes: list[str] = []
    try:
        with pdfplumber.open(stream) as pdf:
            for page in pdf.pages[:30]:
                txt = page.extract_text() or ''
                if txt.strip():
                    partes.append(txt.strip())
    except Exception:
        logger.exception('Falha ao extrair texto do PDF de orçamento')
        return ''
    return '\n\n'.join(partes)
