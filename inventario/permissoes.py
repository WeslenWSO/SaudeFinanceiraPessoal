"""Inventário físico do estoque — somente administradores."""

from __future__ import annotations

from django.contrib.auth.models import User


def usuario_pode_inventario(user: User | None) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def validar_senha_administrador_inventario(user: User | None, senha: str) -> tuple[bool, str]:
    """Confirma ação crítica (aplicar contagem no estoque) com a senha do admin logado."""
    senha = (senha or '').strip()
    if not usuario_pode_inventario(user):
        return False, 'Somente administradores podem aplicar a contagem ao estoque.'
    if not senha:
        return False, 'Informe a senha do administrador para confirmar.'
    if user.check_password(senha):
        return True, ''
    return False, 'Senha incorreta.'
