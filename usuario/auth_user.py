"""Helpers para alinhar usuario.Usuario, auth.User e permissões de menu."""

from django.contrib.auth.models import User

from .models import Usuario


def usuario_login_canonico(user: User | None) -> User | None:
    """Um único auth.User por login, ignorando diferença de maiúsculas."""
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
        return None
    username = (user.username or '').strip()
    if not username:
        return user
    return User.objects.filter(username__iexact=username).order_by('id').first() or user


def auth_user_de_usuario(usuario: Usuario | None) -> User | None:
    if not usuario:
        return None
    username = (usuario.usuario or '').strip()
    if not username:
        return None
    return User.objects.filter(username__iexact=username).order_by('id').first()


def usuarios_login_mesmo_nome(user: User | None) -> list[User]:
    if not user:
        return []
    username = (user.username or '').strip()
    if not username:
        return [user]
    return list(User.objects.filter(username__iexact=username).order_by('id'))
