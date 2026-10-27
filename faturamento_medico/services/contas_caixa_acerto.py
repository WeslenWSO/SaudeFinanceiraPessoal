"""Contas bancárias usadas no Acerto de Caixa (Caixa local ou Outros no Conta Azul)."""
from __future__ import annotations

import logging

from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError

from extrato.models import ContaBancaria

logger = logging.getLogger(__name__)

_TIPOS_ACERTO_CAIXA = ('CAIXA', 'OUTROS')


def conta_elegivel_acerto_caixa(conta: ContaBancaria) -> bool:
    if conta.tipo in _TIPOS_ACERTO_CAIXA:
        return True
    return 'caixa' in (conta.descricao or '').lower()


def conta_ativa_no_acerto_caixa(conta: ContaBancaria) -> bool:
    if not conta_elegivel_acerto_caixa(conta):
        return False
    if getattr(conta, 'inativo_acerto_caixa', False):
        return False
    return (conta.status or 'A') != 'I'


def queryset_contas_caixa_cadastro(empresa_id: int):
    """Todas as contas elegíveis ao acerto (inclui marcadas inativas)."""
    return (
        ContaBancaria.objects.filter(empresa_id=empresa_id)
        .filter(Q(tipo__in=_TIPOS_ACERTO_CAIXA) | Q(descricao__icontains='caixa'))
        .select_related('banco')
        .order_by('descricao', 'id')
    )


def queryset_contas_caixa(empresa_id: int):
    """Somente caixas ativos no acerto (inativos não entram no filtro)."""
    qs = queryset_contas_caixa_cadastro(empresa_id).filter(status='A')
    try:
        return qs.filter(inativo_acerto_caixa=False)
    except (ProgrammingError, OperationalError):
        logger.warning('Coluna inativo_acerto_caixa ausente — migrate extrato 0029+')
        return qs


def caixa_valor_ativo_no_acerto(empresa_id: int, valor: str) -> bool:
    """True se o valor de caixa_acerto pode aparecer no filtro / select da grade."""
    valor = (valor or '').strip()
    if not valor or not valor.isdigit():
        return False
    conta = queryset_contas_caixa_cadastro(empresa_id).filter(pk=int(valor)).first()
    return conta is not None and conta_ativa_no_acerto_caixa(conta)


def rotulo_conta_caixa(conta: ContaBancaria) -> str:
    desc = (conta.descricao or '').strip()
    if desc:
        return desc
    if conta.conta:
        return f'Caixa {conta.conta}'
    return str(conta)


def caixas_acerto_choices(empresa_id: int) -> list[tuple[str, str]]:
    try:
        return [
            (str(conta.pk), rotulo_conta_caixa(conta))
            for conta in queryset_contas_caixa_cadastro(empresa_id)
            if conta_ativa_no_acerto_caixa(conta)
        ]
    except (ProgrammingError, OperationalError):
        logger.exception('Falha ao listar caixas (migrate extrato/faturamento?) empresa=%s', empresa_id)
        from faturamento_medico.models import CAIXAS_ACERTO_CHOICES

        return list(CAIXAS_ACERTO_CHOICES)


def caixas_acerto_valores(empresa_id: int) -> frozenset[str]:
    return frozenset(str(pk) for pk in queryset_contas_caixa(empresa_id).values_list('pk', flat=True))


def conta_caixa_valida(empresa_id: int, valor: str) -> bool:
    valor = (valor or '').strip()
    if not valor or not valor.isdigit():
        return False
    return queryset_contas_caixa(empresa_id).filter(pk=int(valor)).exists()


def rotulo_caixa_acerto_valor(valor: str, empresa_id: int) -> str:
    valor = (valor or '').strip()
    if not valor:
        return ''
    if valor.isdigit():
        conta = queryset_contas_caixa_cadastro(empresa_id).filter(pk=int(valor)).first()
        if conta:
            return rotulo_conta_caixa(conta)
    from faturamento_medico.models import CAIXAS_ACERTO_CHOICES

    for legado, rotulo in CAIXAS_ACERTO_CHOICES:
        if legado == valor:
            return rotulo
    return valor
