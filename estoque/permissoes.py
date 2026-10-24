"""Permissões de estoque operacional."""

from __future__ import annotations

from django.contrib.auth.models import User

from estoque.models import SetorEstoqueResponsavel
from estoque.setores import SetorEstoque

# Usuários de login cujas senhas autorizam estorno de entrada NF (confirmação explícita).
_USUARIOS_SENHA_ESTORNO_NF = ('admin', 'saude')


def usuario_e_admin_estoque(user: User) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.is_staff))


def usuario_responsavel_setor(user: User, empresa_id: int, setor: str) -> bool:
    if usuario_e_admin_estoque(user):
        return True
    if setor == SetorEstoque.FARMACIA:
        return False
    return SetorEstoqueResponsavel.objects.filter(
        empresa_id=empresa_id,
        setor=setor,
        usuario=user,
    ).exists()


def usuario_pode_requisicao_farmacia(user: User) -> bool:
    if usuario_e_admin_estoque(user):
        return True
    from usuario.menu import usuario_pode_menu

    return usuario_pode_menu(user, 'estoque_requisicoes')


def usuario_pode_baixa_setor(user: User, empresa_id: int, setor: str) -> bool:
    return usuario_responsavel_setor(user, empresa_id, setor)


def validar_senha_aprovacao_estorno_nf(senha: str) -> tuple[bool, str]:
    """
    Estorno de NF exige senha de um dos logins Admin ou Saude (username, case insensitive).
    """
    senha = (senha or '').strip()
    if not senha:
        return False, 'Informe a senha do Admin ou Saude para estornar.'
    for username in _USUARIOS_SENHA_ESTORNO_NF:
        user = User.objects.filter(username__iexact=username).first()
        if user and user.is_active and user.check_password(senha):
            return True, ''
    return False, 'Senha incorreta. Somente Admin ou Saude podem autorizar o estorno.'
