"""Flags e período da tela Sincronizar Conta Azul (POST/GET)."""

from __future__ import annotations

from datetime import date

SYNC_FLAGS = (
    'cadastros',
    'receitas',
    'despesas',
    'transferencias',
    'vendas',
    'nfse_prestador',
)

SYNC_FLAG_LABELS = {
    'cadastros': 'Cadastros',
    'receitas': 'Receitas (CAR)',
    'despesas': 'Despesas (CAP)',
    'transferencias': 'Transferências',
    'vendas': 'Pedidos de venda',
    'nfse_prestador': 'NFS-e prestador',
}

# Padrão da tela quando não há query string (espelha o HTML inicial)
SYNC_FLAGS_PADRAO = {
    'cadastros': False,
    'receitas': True,
    'despesas': True,
    'transferencias': False,
    'vendas': True,
    'nfse_prestador': False,
}


def flags_from_post(request) -> dict[str, bool]:
    """Somente checkboxes marcados vêm no POST — cada flag é independente."""
    return {nome: nome in request.POST for nome in SYNC_FLAGS}


def flags_from_get(request) -> dict[str, bool] | None:
    """Query ?receitas=1&despesas=0 — None se nenhum parâmetro de flag na URL."""
    if not any(f'{nome}' in request.GET for nome in SYNC_FLAGS):
        return None
    return {nome: request.GET.get(nome) == '1' for nome in SYNC_FLAGS}


def flags_para_template(request) -> dict[str, bool]:
    from_get = flags_from_get(request)
    if from_get is not None:
        return from_get
    return dict(SYNC_FLAGS_PADRAO)


def montar_opcoes_sync(
    flags: dict[str, bool],
    *,
    data_de: date,
    data_ate: date,
) -> dict:
    return {
        **{nome: bool(flags.get(nome)) for nome in SYNC_FLAGS},
        'data_de': data_de,
        'data_ate': data_ate,
    }


def alguma_flag_ativa(flags: dict[str, bool]) -> bool:
    return any(flags.get(nome) for nome in SYNC_FLAGS)


def precisa_periodo(flags: dict[str, bool]) -> bool:
    return any(
        flags.get(nome)
        for nome in ('receitas', 'despesas', 'transferencias', 'vendas', 'nfse_prestador')
    )


def resumo_flags(flags: dict[str, bool]) -> str:
    partes = [SYNC_FLAG_LABELS[n] for n in SYNC_FLAGS if flags.get(n)]
    return ', '.join(partes) if partes else 'nenhum item'


def query_flags(flags: dict[str, bool]) -> str:
    return '&'.join(f'{nome}={"1" if flags.get(nome) else "0"}' for nome in SYNC_FLAGS)


def dica_atualizar_pos_sync(flags: dict[str, bool]) -> str:
    """Texto pós-sync alinhado às flags marcadas (sem citar CAR/CAP se não foram pedidos)."""
    partes: list[str] = []
    if flags.get('receitas'):
        partes.append('Contas a Receber')
    if flags.get('despesas'):
        partes.append('Contas a Pagar')
    if flags.get('transferencias'):
        partes.append('Transferências')
    if flags.get('nfse_prestador'):
        partes.append('a lista de Notas Fiscais (NFSe)')
    if flags.get('vendas'):
        partes.append('Notas Fiscais (dados de pagamento/caixa das vendas)')
    if flags.get('cadastros'):
        partes.append('cadastros (clientes, fornecedores, categorias, contas)')
    if not partes:
        return 'Aguarde 1–3 minutos até a conclusão.'
    if len(partes) == 1:
        alvo = partes[0]
    else:
        alvo = ', '.join(partes[:-1]) + ' e ' + partes[-1]
    return f'Aguarde 1–3 minutos e atualize {alvo}.'
