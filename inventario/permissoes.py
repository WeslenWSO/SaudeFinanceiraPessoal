"""Permissões do inventário de estoque."""

from __future__ import annotations

from django.contrib.auth.models import User

CODIGO_MENU_INVENTARIO = 'inventario'

# Logins que podem autorizar aplicar contagem (além de staff/superuser).
_LOGINS_ADMIN_APLICAR_ESTOQUE = ('admin', 'saude')


def usuario_pode_acessar_inventario(user: User | None) -> bool:
    from usuario.menu import usuario_pode_menu

    return usuario_pode_menu(user, CODIGO_MENU_INVENTARIO)


# Alias usado em mixins/decorators legados.
usuario_pode_inventario = usuario_pode_acessar_inventario


def usuario_pode_aplicar_contagem_estoque(user: User | None) -> bool:
    """Quem pode ver/usar o botão de aplicar (credencial admin é validada no POST)."""
    return usuario_pode_acessar_inventario(user)


def validar_credencial_aplicar_inventario(
    username: str,
    senha: str,
) -> tuple[bool, str, User | None]:
    """Exige login e senha de um administrador (staff/superuser ou Admin/Saude)."""
    login = (username or '').strip()
    senha = (senha or '').strip()
    if not login or not senha:
        return False, 'Informe usuário e senha do administrador.', None

    user = User.objects.filter(username__iexact=login).first()
    if not user or not user.is_active:
        return False, 'Usuário administrador não encontrado.', None

    login_lower = login.lower()
    eh_admin = user.is_superuser or user.is_staff or login_lower in _LOGINS_ADMIN_APLICAR_ESTOQUE
    if not eh_admin:
        return False, 'Somente administrador pode aplicar a contagem ao estoque.', None
    if not user.check_password(senha):
        return False, 'Senha incorreta.', None
    return True, '', user
