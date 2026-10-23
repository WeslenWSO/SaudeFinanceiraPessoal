"""Inventário físico do estoque — somente administradores."""

from __future__ import annotations

from django.contrib.auth.models import User


def usuario_pode_inventario(user: User | None) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))
