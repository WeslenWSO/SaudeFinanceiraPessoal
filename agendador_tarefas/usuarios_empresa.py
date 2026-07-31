"""Usuários com permissão na empresa (UsuarioEmpresa ativo)."""
from __future__ import annotations

from django.contrib.auth.models import User

from empresa.models import UsuarioEmpresa


def rotulo_responsavel(user: User) -> str:
    """Nome gravado no campo responsavel (compatível com o letreiro)."""
    nome = (user.get_full_name() or '').strip()
    if nome:
        return nome
    return (user.username or '').strip()


def opcoes_responsavel_empresa(empresa_id: int | None, valor_atual: str = '') -> list[tuple[str, str]]:
    """
    Opções para o select de responsável: usuários com UsuarioEmpresa ativo na empresa.
    """
    opcoes: list[tuple[str, str]] = [('', '— Selecione —')]
    vistos: set[str] = set()

    qs = UsuarioEmpresa.objects.filter(ativo=True).select_related('usuario')
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    qs = qs.order_by('usuario__first_name', 'usuario__last_name', 'usuario__username')

    for ue in qs:
        user = ue.usuario
        if not user.is_active:
            continue
        valor = rotulo_responsavel(user)
        if not valor or valor in vistos:
            continue
        vistos.add(valor)
        if user.get_full_name() and user.username and user.username != valor:
            rotulo = f'{valor} ({user.username})'
        else:
            rotulo = valor
        opcoes.append((valor, rotulo))

    atual = (valor_atual or '').strip()
    if atual and atual not in vistos:
        opcoes.append((atual, f'{atual} (atual — fora da lista)'))

    return opcoes
