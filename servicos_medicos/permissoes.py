"""Permissões do módulo serviços médicos."""

from __future__ import annotations

from django.contrib.auth.models import User

_USUARIO_GRID_TABELA_PRECO = "saude"


def usuario_pode_editar_tabela_preco_grid(user: User | None) -> bool:
    """Superusuário ou login Saude — edição inline na lista de preços."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return (user.username or "").strip().lower() == _USUARIO_GRID_TABELA_PRECO
