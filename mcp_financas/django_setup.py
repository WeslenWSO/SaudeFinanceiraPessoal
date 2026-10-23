"""Inicializa Django antes de tools MCP ou LLM."""

from __future__ import annotations

import os


def setup_django() -> None:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
    import django

    django.setup()
