"""Persistência de permissões de menu por auth.User."""

from django.contrib.auth.models import User
from django.db import transaction

from usuario.auth_user import auth_user_de_usuario, usuario_login_canonico
from usuario.menu import CODIGOS_MENU, MARCADOR_MENU_CONFIGURADO
from .models import PermissaoMenuUsuario, Usuario

MARCADOR_CONFIGURADO = MARCADOR_MENU_CONFIGURADO


def permissoes_salvas(user: User | None) -> set[str]:
    if not user:
        return set()
    user = usuario_login_canonico(user)
    if not user:
        return set()
    return set(
        PermissaoMenuUsuario.objects.filter(usuario=user)
        .exclude(codigo=MARCADOR_CONFIGURADO)
        .values_list('codigo', flat=True)
    )


def tem_permissoes_configuradas(user: User | None) -> bool:
    if not user:
        return False
    user = usuario_login_canonico(user)
    if not user:
        return False
    return PermissaoMenuUsuario.objects.filter(
        usuario=user,
        codigo=MARCADOR_CONFIGURADO,
    ).exists()


def permissoes_para_formulario(usuario: Usuario) -> set[str]:
    """Valores iniciais dos checkboxes ao editar usuario.Usuario."""
    user = auth_user_de_usuario(usuario)
    if not user:
        return set(CODIGOS_MENU)
    if not tem_permissoes_configuradas(user):
        if PermissaoMenuUsuario.objects.filter(usuario=user).exists():
            return permissoes_salvas(user)
        return set(CODIGOS_MENU)
    return permissoes_salvas(user)


def salvar_permissoes_menu(
    usuario: Usuario,
    codigos: list[str],
    *,
    user: User | None = None,
) -> None:
    if user is None:
        user = auth_user_de_usuario(usuario)
    user = usuario_login_canonico(user)
    if not user:
        return

    validos = {c for c in codigos if c in CODIGOS_MENU}
    novos = [
        PermissaoMenuUsuario(usuario=user, codigo=codigo)
        for codigo in sorted(validos)
    ]
    novos.append(PermissaoMenuUsuario(usuario=user, codigo=MARCADOR_CONFIGURADO))

    with transaction.atomic():
        PermissaoMenuUsuario.objects.filter(usuario=user).delete()
        if novos:
            PermissaoMenuUsuario.objects.bulk_create(novos)

