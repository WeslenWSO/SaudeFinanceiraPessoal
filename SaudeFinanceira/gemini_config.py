"""Resolução centralizada da API Gemini (env ou banco)."""
from __future__ import annotations

from django.conf import settings


def get_gemini_api_key() -> str:
    """Prioridade: GEMINI_API_KEY no ambiente; depois registro no Postgres."""
    env = (getattr(settings, 'GEMINI_API_KEY', None) or '').strip()
    if env:
        return env
    try:
        from dashboard.models import GeminiConfig

        return (GeminiConfig.get_solo().api_key or '').strip()
    except Exception:
        return ''


def get_gemini_model() -> str:
    env = (getattr(settings, 'GEMINI_MODEL', None) or '').strip()
    if env:
        return env
    try:
        from dashboard.models import GeminiConfig

        model = (GeminiConfig.get_solo().model_name or '').strip()
        if model:
            return model
    except Exception:
        pass
    return 'gemini-2.5-flash'
