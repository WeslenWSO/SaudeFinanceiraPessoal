"""Permissões de estoque operacional."""

from __future__ import annotations

from django.contrib.auth.models import User

from estoque.models import SetorEstoqueResponsavel
from estoque.setores import SetorEstoque


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
