"""Forma de pagamento Conta Azul → modelo Cobranca (sync financeiro e venda/NFS-e)."""

from __future__ import annotations

from cobranca.models import Cobranca

METODO_PAGAMENTO_CA = {
    'DINHEIRO': 'Dinheiro',
    'CARTAO_CREDITO': 'Cartão de Crédito',
    'CARTAO_CREDITO_VIA_LINK': 'Cartão de Crédito (Link)',
    'CARTAO_DEBITO': 'Cartão de Débito',
    'BOLETO_BANCARIO': 'Boleto Bancário',
    'CHEQUE': 'Cheque',
    'TRANSFERENCIA_BANCARIA': 'Transferência Bancária',
    'PIX_PAGAMENTO_INSTANTANEO': 'PIX',
    'PIX_COBRANCA': 'PIX Cobrança',
    'CARTEIRA_DIGITAL': 'Carteira Digital',
    'DEPOSITO_BANCARIO': 'Depósito Bancário',
    'DEBITO_AUTOMATICO': 'Débito Automático',
    'VALE_ALIMENTACAO': 'Vale Alimentação',
    'VALE_REFEICAO': 'Vale Refeição',
    'VALE_COMBUSTIVEL': 'Vale Combustível',
    'VALE_PRESENTE': 'Vale Presente',
    'SEM_PAGAMENTO': 'Sem Pagamento',
    'OUTRO': 'Outro',
}


def _label_metodo_pagamento_ca(codigo: str) -> str:
    codigo = (codigo or '').strip().upper()
    if not codigo:
        return ''
    if codigo in METODO_PAGAMENTO_CA:
        return METODO_PAGAMENTO_CA[codigo]
    return codigo.replace('_', ' ').title()


def _metodo_pagamento_da_categoria(item: dict) -> str:
    """Heurística a partir do nome da categoria CA (ex.: CONVENIO - CARTAO CREDITO)."""
    cats = item.get('categorias') or []
    if not cats or not isinstance(cats[0], dict):
        return ''
    nome = str(cats[0].get('nome') or '').upper()
    nome = (
        nome.replace('Á', 'A').replace('À', 'A').replace('Ã', 'A')
        .replace('É', 'E').replace('Í', 'I').replace('Ó', 'O')
        .replace('Ú', 'U').replace('Ç', 'C')
    )
    if 'PIX' in nome:
        return 'PIX'
    if 'BOLETO' in nome:
        return 'Boleto Bancário'
    if 'DINHEIRO' in nome:
        return 'Dinheiro'
    if 'TRANSFERENCIA' in nome:
        return 'Transferência Bancária'
    if 'CHEQUE' in nome:
        return 'Cheque'
    if 'DEBITO' in nome or 'DEBIT' in nome:
        return 'Cartão de Débito'
    if 'CARTAO' in nome or 'CREDITO' in nome or 'CREDIT' in nome:
        return 'Cartão de Crédito'
    return ''


def _texto_forma_pagamento_item(item: dict) -> str:
    metodo = _label_metodo_pagamento_ca(str(item.get('metodo_pagamento') or ''))
    if metodo:
        return metodo[:50]
    for baixa in reversed(item.get('baixas') or []):
        if isinstance(baixa, dict):
            metodo = _label_metodo_pagamento_ca(str(baixa.get('metodo_pagamento') or ''))
            if metodo:
                return metodo[:50]
    for key in ('forma_pagamento', 'meio_pagamento', 'tipo_pagamento', 'forma_recebimento'):
        raw = item.get(key)
        if isinstance(raw, dict):
            texto = str(raw.get('nome') or raw.get('descricao') or raw.get('tipo') or '').strip()
            if texto:
                return texto[:50]
        elif isinstance(raw, str) and raw.strip():
            return raw.strip()[:50]
    metodo_cat = _metodo_pagamento_da_categoria(item)
    if metodo_cat:
        return metodo_cat[:50]
    return ''


def _cobranca_de_item(item: dict, cache: dict[str, Cobranca] | None = None) -> Cobranca | None:
    texto = _texto_forma_pagamento_item(item)
    if not texto:
        return None
    if cache is not None:
        chave = texto.casefold()
        if chave in cache:
            return cache[chave]
    cob = Cobranca.objects.filter(descricao__iexact=texto).first()
    if cob:
        if cache is not None:
            cache[texto.casefold()] = cob
        return cob
    cob = Cobranca.objects.create(descricao=texto[:50], tpag='99', formapgto='0')
    if cache is not None:
        cache[texto.casefold()] = cob
    return cob
