"""Sincroniza usuario.Usuario (cadastro da empresa) com auth.User (login)."""

from django.contrib.auth.models import User

from empresa.models import UsuarioEmpresa

from .models import Usuario


def sincronizar_login_usuario(usuario: Usuario, senha: str | None = None) -> User:
    """
    Cria ou atualiza auth.User e vincula à empresa via UsuarioEmpresa.
    Se senha for informada, redefine a senha de login.
    """
    username = (usuario.usuario or '').strip()
    if not username:
        raise ValueError('Nome de usuario (login) nao pode ser vazio.')

    user, _created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': usuario.email or '',
            'last_name': usuario.lastname or '',
            'is_active': True,
        },
    )
    user.email = usuario.email or user.email
    user.last_name = usuario.lastname or user.last_name
    user.is_active = True
    if senha:
        user.set_password(senha)
    user.save()

    if usuario.empresa_id:
        UsuarioEmpresa.objects.get_or_create(
            usuario=user,
            empresa_id=usuario.empresa_id,
            defaults={'ativo': True},
        )

    return user
