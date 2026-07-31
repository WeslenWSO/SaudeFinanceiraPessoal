"""Helpers para alinhar usuario.Usuario, auth.User e permissões de menu."""

from django.contrib.auth.models import User

from .models import PermissaoMenuUsuario, Usuario


def usuario_login_canonico(user: User | None) -> User | None:
    """Um único auth.User por login, ignorando diferença de maiúsculas."""
    if not user:
        return None
    username = (user.username or '').strip()
    if not username:
        return user if getattr(user, 'pk', None) else None
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


def consolidar_auth_users_duplicados(manter: User, *, login: str | None = None) -> User:
    """
    Remove auth.User duplicados (mesmo login, case diferente) e move permissões
    de menu para o usuário canônico.
    """
    chave = (login or manter.username or '').strip()
    if not chave or not manter.pk:
        return manter

    duplicados = list(
        User.objects.filter(username__iexact=chave).exclude(pk=manter.pk).order_by('id')
    )
    for dup in duplicados:
        for perm in PermissaoMenuUsuario.objects.filter(usuario=dup):
            PermissaoMenuUsuario.objects.get_or_create(
                usuario=manter,
                codigo=perm.codigo,
            )
            perm.delete()
        dup.delete()
    return manter
