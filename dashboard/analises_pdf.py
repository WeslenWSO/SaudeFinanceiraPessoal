"""Geração de PDF para relatório de análises (Playwright quando disponível)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def html_para_pdf_bytes(html: str, *, base_url: str | None = None) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            'Playwright não instalado. Use «Apresentação» e imprima como PDF, '
            'ou instale: pip install playwright && playwright install chromium'
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            if base_url:
                page.set_content(html, wait_until='load', timeout=120_000)
            else:
                page.set_content(html, wait_until='load', timeout=120_000)
            page.wait_for_timeout(2500)
            return page.pdf(
                format='A4',
                print_background=True,
                margin={'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'},
            )
        finally:
            browser.close()
