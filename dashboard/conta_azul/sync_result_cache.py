"""Resultado da sync Conta Azul em background → mensagem na próxima visita (cache)."""

from __future__ import annotations

from django.core.cache import cache

_SYNC_MSG_TTL = 3600


def chave_mensagem_sync(empresa_id: int) -> str:
    return f'conta_azul_sync_msg_{int(empresa_id)}'


def gravar_mensagem_sync(empresa_id: int, nivel: str, texto: str) -> None:
    if not texto:
        return
    cache.set(
        chave_mensagem_sync(empresa_id),
        {'nivel': nivel or 'info', 'texto': texto},
        _SYNC_MSG_TTL,
    )


def consumir_mensagem_sync(empresa_id: int) -> dict | None:
    chave = chave_mensagem_sync(empresa_id)
    payload = cache.get(chave)
    if payload:
        cache.delete(chave)
    return payload


def aplicar_mensagem_sync_cache(request, empresa_id: int) -> None:
    """Exibe mensagem Django messages se a sync em background terminou."""
    from django.contrib import messages

    payload = consumir_mensagem_sync(empresa_id)
    if not payload:
        return
    texto = (payload.get('texto') or '').strip()
    if not texto:
        return
    nivel = payload.get('nivel') or 'info'
    getattr(messages, nivel, messages.info)(request, texto)
