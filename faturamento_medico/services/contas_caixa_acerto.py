"""Contas bancárias tipo Caixa usadas no Acerto de Caixa."""
from __future__ import annotations

from extrato.models import ContaBancaria


def queryset_contas_caixa(empresa_id: int):
    return (
        ContaBancaria.objects.filter(
            empresa_id=empresa_id,
            tipo='CAIXA',
            status='A',
        )
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
        conta = (
            ContaBancaria.objects.filter(pk=int(valor), empresa_id=empresa_id, tipo='CAIXA')
            .first()
        )
        if conta:
            return rotulo_conta_caixa(conta)
    from faturamento_medico.models import CAIXAS_ACERTO_CHOICES

    for legado, rotulo in CAIXAS_ACERTO_CHOICES:
        if legado == valor:
            return rotulo
    return valor
