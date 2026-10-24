"""Geração de PDF para relatório de análises (Playwright quando disponível)."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_CHROMIUM_ARGS = (
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
)


def _launch_chromium(playwright):
    return playwright.chromium.launch(
        headless=True,
        args=list(_CHROMIUM_ARGS),
    )


def html_para_pdf_bytes(html: str, *, base_url: str | None = None) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            'Playwright não instalado. Use «Apresentação» e imprima como PDF, '
            'ou instale: pip install playwright && playwright install chromium'
        ) from exc

    browsers_path = (os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '').strip()
    if browsers_path:
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path

    try:
        with sync_playwright() as pw:
            browser = _launch_chromium(pw)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until='domcontentloaded', timeout=120_000)
                try:
                    page.wait_for_load_state('networkidle', timeout=45_000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)
                return page.pdf(
                    format='A4',
                    print_background=True,
                    margin={
                        'top': '12mm',
                        'bottom': '12mm',
                        'left': '10mm',
                        'right': '10mm',
                    },
                )
            finally:
                browser.close()
    except Exception as exc:
        logger.exception('Falha ao gerar PDF de análises (Playwright/Chromium)')
        hint = (
            'No servidor, confira se o build instalou o Chromium '
            '(PLAYWRIGHT_BROWSERS_PATH e playwright install chromium).'
        )
        raise RuntimeError(f'Não foi possível gerar o PDF. {hint} Detalhe: {exc}') from exc
