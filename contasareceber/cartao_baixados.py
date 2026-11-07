"""Filtros e regras para a tela de conciliação cartão em títulos já baixados (pago)."""
from __future__ import annotations

from django.db.models import Count, QuerySet

from contasareceber.cartao_aproximacao import _ascii_fold_upper, tipo_cartao_conta
from contasareceber.models import ContaAReceber


def conta_eh_cartao_credito_ou_debito(conta: ContaAReceber) -> bool:
    """Cobrança crédito ou débito (CAR ou NF)."""
    desc = _ascii_fold_upper(conta.get_cobranca_exibicao())
    if not desc:
        return False
    if 'DEBIT' in desc or 'DEBITO' in desc:
        return True
    if 'CREDIT' in desc or 'CREDITO' in desc:
        return True
    if 'CART' in desc and ('DEBIT' in desc or 'CREDIT' in desc or 'DEBITO' in desc or 'CREDITO' in desc):
        return True
    return False


def queryset_cartao_pago_base(empresa_id: int) -> QuerySet:
    return (
        ContaAReceber.objects.filter(empresa_id=empresa_id, status='pago')
        .select_related('forma_pagamento', 'nota', 'nota__forma_pagamento')
        .annotate(n_recebiveis_maquina=Count('relatoriorecebiveismaquinacartao', distinct=True))
    )


def filtrar_por_tipo_cartao(contas: list[ContaAReceber], tipo: str) -> list[ContaAReceber]:
    """tipo: '' | 'debito' | 'credito' — inclui cobrança só na NF."""
    contas = [c for c in contas if conta_eh_cartao_credito_ou_debito(c)]
    if tipo not in ('debito', 'credito'):
        return contas
    return [c for c in contas if tipo_cartao_conta(c) == tipo]


def extrair_filtros_conciliar_cartao_baixados(request) -> dict:
    return {
        'search': (request.GET.get('search') or '').strip(),
        'receb_inicio': (request.GET.get('receb_inicio') or '').strip(),
        'receb_fim': (request.GET.get('receb_fim') or '').strip(),
        'venc_inicio': (request.GET.get('venc_inicio') or '').strip(),
        'venc_fim': (request.GET.get('venc_fim') or '').strip(),
        'tipo_cartao': (request.GET.get('tipo_cartao') or '').strip(),
        'sem_maquininha': request.GET.get('sem_maquininha') == '1',
        'per_page': (request.GET.get('per_page') or '50').strip(),
        'tem_get': bool(request.GET),
    }
