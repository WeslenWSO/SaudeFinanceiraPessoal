"""Contas bancárias usadas no Acerto de Caixa (Caixa local ou Outros no Conta Azul)."""
from __future__ import annotations

from django.db.models import Q

from extrato.models import ContaBancaria

_TIPOS_ACERTO_CAIXA = ('CAIXA', 'OUTROS')


def queryset_contas_caixa(empresa_id: int):
    return (
        ContaBancaria.objects.filter(
            empresa_id=empresa_id,
            status='A',
        )
        .filter(Q(tipo__in=_TIPOS_ACERTO_CAIXA) | Q(descricao__icontains='caixa'))
        .select_related('banco')
        .order_by('descricao', 'id')
    )


def rotulo_conta_caixa(conta: ContaBancaria) -> str:
    desc = (conta.descricao or '').strip()
    if desc:
        return desc
    if conta.conta:
        return f'Caixa {conta.conta}'
    return str(conta)


def caixas_acerto_choices(empresa_id: int) -> list[tuple[str, str]]:
    return [
        (str(conta.pk), rotulo_conta_caixa(conta))
        for conta in queryset_contas_caixa(empresa_id)
    ]


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
        conta = queryset_contas_caixa(empresa_id).filter(pk=int(valor)).first()
        if conta:
            return rotulo_conta_caixa(conta)
    from faturamento_medico.models import CAIXAS_ACERTO_CHOICES

    for legado, rotulo in CAIXAS_ACERTO_CHOICES:
        if legado == valor:
            return rotulo
    return valor
