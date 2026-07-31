"""Persistência de permissões de menu por auth.User."""

from django.contrib.auth.models import User

from .menu import CODIGOS_MENU, auth_user_de_usuario
from .models import PermissaoMenuUsuario, Usuario


def permissoes_salvas(user: User | None) -> set[str]:
    if not user:
        return set()
    return set(
        PermissaoMenuUsuario.objects.filter(usuario=user).values_list('codigo', flat=True)
    )


def tem_permissoes_configuradas(user: User | None) -> bool:
    if not user:
        return False
    return PermissaoMenuUsuario.objects.filter(usuario=user).exists()


def permissoes_para_formulario(usuario: Usuario) -> set[str]:
    """Valores iniciais dos checkboxes ao editar usuario.Usuario."""
    user = auth_user_de_usuario(usuario)
    if not user:
        return set(CODIGOS_MENU)
    if not tem_permissoes_configuradas(user):
        return set(CODIGOS_MENU)
    return permissoes_salvas(user)


def salvar_permissoes_menu(usuario: Usuario, codigos: list[str]) -> None:
    user = auth_user_de_usuario(usuario)
    if not user:
        return
    validos = {c for c in codigos if c in CODIGOS_MENU}
    PermissaoMenuUsuario.objects.filter(usuario=user).exclude(codigo__in=validos).delete()
    existentes = set(
        PermissaoMenuUsuario.objects.filter(usuario=user).values_list('codigo', flat=True)
    )
    novos = [
        PermissaoMenuUsuario(usuario=user, codigo=codigo)
        for codigo in validos
        if codigo not in existentes
    ]
    if novos:
        PermissaoMenuUsuario.objects.bulk_create(novos)
