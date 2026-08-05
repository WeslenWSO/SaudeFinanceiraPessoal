"""Importação de cadastros e lançamentos Conta Azul → models locais."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, TypeVar

from django.db import IntegrityError, OperationalError, connection
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

T = TypeVar('T')


def _com_retry_sqlite(fn: Callable[[], T], *, tentativas: int = 6) -> T:
    """Repete em 'database is locked' (SQLite + OneDrive / sync longo)."""
    ultimo: Exception | None = None
    for i in range(tentativas):
        try:
            return fn()
        except OperationalError as exc:
            ultimo = exc
            if 'locked' not in str(exc).lower():
                raise
            try:
                connection.close()
            except Exception:
                pass
            time.sleep(0.4 * (i + 1))
    assert ultimo is not None
    raise ultimo

from categoria.models import Categoria, CentroCusto
from cliente.models import Cliente
from cobranca.models import Cobranca
from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber
from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from extrato.models import Banco, ContaBancaria, Lancamento
from fornecedor.models import Fornecedor


TIPO_CONTA_MAP = {
    'CONTA_CORRENTE': 'CONTA_CORRENTE',
    'POUPANCA': 'POUPANCA',
    'CAIXINHA': 'CAIXA',
    'INVESTIMENTO': 'INVESTIMENTO',
    'CARTAO_CREDITO': 'FATURA_CARTAO',
    'APLICACAO': 'INVESTIMENTO',
    'OUTROS': 'CONTA_CORRENTE',
}

STATUS_RECEITA_MAP = {
    'EM_ABERTO': 'pendente',
    'RECEBIDO': 'pago',
    'RECEBIDO_PARCIAL': 'pendente',
    'ATRASADO': 'vencido',
    'PERDIDO': 'cancelado',
    'RENEGOCIADO': 'pendente',
    'ACQUITTED': 'pago',
    'QUITADO': 'pago',
}

_RE_UUID = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)
_RE_DESC_VENDA = re.compile(r'Venda\s+(\d+)', re.IGNORECASE)
_RE_DESC_NFSE = re.compile(r'NFS-e\s*:\s*(\d+)', re.IGNORECASE)
_RE_DESC_NFE = re.compile(r'NF-?e?\s*[:#]?\s*(\d+)', re.IGNORECASE)
_RE_DESC_NF = re.compile(r'(?:nota fiscal|\bnf\b)\s*[:#nº°]?\s*(\d+)', re.IGNORECASE)

# Limite de GET /parcelas/{id} por execução (NSU em títulos pagos; evita timeout no Render).
LIMITE_DETALHE_PARCELA_SYNC = 15

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

STATUS_DESPESA_MAP = {
    'EM_ABERTO': 'pendente',
    'PAGO': 'pago',
    'PAGO_PARCIAL': 'pendente',
    'ATRASADO': 'vencido',
    'CANCELADO': 'cancelado',
    'ACQUITTED': 'pago',
    'QUITADO': 'pago',
    'RECEBIDO': 'pago',
}


def _status_api_item(item: dict) -> str:
    return str(
        item.get('status_traduzido') or item.get('status') or item.get('situacao') or 'EM_ABERTO'
    ).upper().strip()


def _valor_pago_item(item: dict) -> Decimal:
    pago = _parse_decimal(item.get('pago') or item.get('valor_pago') or item.get('valorPago'))
    if pago > 0:
        return pago
    status = _status_api_item(item)
    if status in ('RECEBIDO', 'PAGO', 'ACQUITTED', 'QUITADO'):
        return _parse_decimal(item.get('total') or item.get('valor') or item.get('valor_liquido'))
    nao_pago = _parse_decimal(item.get('nao_pago'))
    total = _parse_decimal(item.get('total') or item.get('valor') or item.get('valor_liquido'))
    if total > 0 and nao_pago == 0:
        return total
    return Decimal('0')


def _map_status_receita(item: dict) -> str:
    st = _status_api_item(item)
    if st in STATUS_RECEITA_MAP:
        return STATUS_RECEITA_MAP[st]
    if _valor_pago_item(item) > 0:
        return 'pago'
    return 'pendente'


def _map_status_despesa(item: dict) -> str:
    st = _status_api_item(item)
    if st in STATUS_DESPESA_MAP:
        return STATUS_DESPESA_MAP[st]
    if _valor_pago_item(item) > 0:
        return 'pago'
    return 'pendente'


def _data_pagamento_item(item: dict, fallback: date) -> date | None:
    dt = _parse_data(
        item.get('data_pagamento') or item.get('data_baixa') or item.get('data_recebimento')
    )
    if dt:
        return dt
    if _valor_pago_item(item) > 0:
        return (
            _parse_data(item.get('data_competencia'))
            or _parse_data(item.get('data_vencimento'))
            or fallback
        )
    return None


def _parse_decimal(valor) -> Decimal:
    if valor is None or valor == '':
        return Decimal('0')
    try:
        return Decimal(str(valor).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _parse_data(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    s = str(valor)[:10]
    return parse_date(s)


def _cobranca_padrao() -> Cobranca:
    cob = Cobranca.objects.order_by('pk').first()
    if cob:
        return cob
    return Cobranca.objects.create(descricao='Conta Azul', tpag='99', formapgto='0')


def _cnpj_sintetico_conta_azul(empresa_id: int, identificador: str) -> str:
    """CNPJ único por empresa/fornecedor CA (fornecedores sem CNPJ na API)."""
    chave = f'ca-forn:{empresa_id}:{identificador}'.encode('utf-8')
    digest = hashlib.sha256(chave).hexdigest()
    nums = ''.join(c for c in digest if c.isdigit())
    while len(nums) < 14:
        nums += digest
    return nums[:14]


def _nome_fornecedor_item(item: dict) -> str:
    forn_raw = item.get('fornecedor')
    if isinstance(forn_raw, dict):
        nome = str(forn_raw.get('nome') or forn_raw.get('razao_social') or forn_raw.get('descricao') or '')
    elif isinstance(forn_raw, str):
        nome = forn_raw
    else:
        nome = ''
    if not nome:
        nome = str(item.get('nome_fornecedor') or 'Fornecedor CA')
    return nome.strip()[:200]


def _nome_cliente_item(empresa, item: dict) -> str:
    cli_raw = item.get('cliente') or item.get('pessoa') or item.get('pagador')
    if isinstance(cli_raw, dict):
        ca_id = str(cli_raw.get('id') or cli_raw.get('uuid') or '').strip()
        if ca_id:
            local = Cliente.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
            if local:
                return local.razao[:200]
        nome = str(
            cli_raw.get('nome')
            or cli_raw.get('razao_social')
            or cli_raw.get('nome_fantasia')
            or cli_raw.get('descricao')
            or ''
        ).strip()
        if nome:
            return nome[:200]
    elif isinstance(cli_raw, str) and cli_raw.strip():
        return cli_raw.strip()[:200]
    nome = str(item.get('nome_cliente') or item.get('cliente_nome') or '').strip()
    if nome:
        return nome[:200]
    return 'Cliente CA'


def _label_metodo_pagamento_ca(codigo: str) -> str:
    codigo = (codigo or '').strip().upper()
    if not codigo:
        return ''
    if codigo in METODO_PAGAMENTO_CA:
        return METODO_PAGAMENTO_CA[codigo]
    return codigo.replace('_', ' ').title()


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


def _aplicar_campos_da_descricao(item: dict) -> dict:
    """Extrai NF/venda da descrição da busca (sem GET extra por parcela)."""
    item = dict(item or {})
    desc = str(item.get('descricao') or '')
    if not desc:
        return item
    fatura = item.get('fatura')
    tem_nf = isinstance(fatura, dict) and str(fatura.get('numero') or '').strip() not in ('', '0')
    m_nf = _RE_DESC_NFSE.search(desc)
    if m_nf and not tem_nf:
        item['fatura'] = {'numero': m_nf.group(1), 'tipo_fatura': 'NFSE'}
    if not _numero_fatura_item(item):
        for rx in (_RE_DESC_NFE, _RE_DESC_NF):
            m = rx.search(desc)
            if m:
                item['fatura'] = {'numero': m.group(1), 'tipo_fatura': 'NFE'}
                break
    evento = item.get('evento') if isinstance(item.get('evento'), dict) else {}
    tem_venda = bool(str(evento.get('codigo_referencia') or item.get('codigo_venda') or '').strip())
    m_v = _RE_DESC_VENDA.search(desc)
    if m_v and not tem_venda:
        ev = dict(evento)
        ev['codigo_referencia'] = m_v.group(1)
        item['evento'] = ev
    return item


def _item_receita_pago(item: dict) -> bool:
    status = str(item.get('status') or '').upper()
    if status in ('RECEBIDO', 'ACQUITTED', 'QUITADO', 'PAGO', 'RECEBIDO_PARCIAL'):
        return True
    try:
        return Decimal(str(item.get('pago') or 0)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _precisa_detalhe_parcela(item: dict) -> bool:
    """Busca detalhe só para NSU em títulos já pagos (forma de pagamento vem da categoria/descrição)."""
    return _item_receita_pago(item) and not _nsu_receita_item(item)


def _mesclar_item_receita(item_busca: dict, item_detalhe: dict) -> dict:
    """Detalhe da parcela (GET por id) sobrescreve campos ausentes no buscar."""
    merged = dict(item_busca or {})
    for key, val in (item_detalhe or {}).items():
        if val is None or val == '' or val == []:
            continue
        merged[key] = val
    return merged


def _enriquecer_item_receita(
    client: ContaAzulClient,
    item: dict,
    cache: dict[str, dict],
) -> dict:
    parcela_id = str(item.get('id') or item.get('id_parcela') or '').strip()
    if not parcela_id:
        return item
    if parcela_id not in cache:
        try:
            cache[parcela_id] = client.buscar_parcela_por_id(parcela_id)
        except ContaAzulAPIError:
            cache[parcela_id] = {}
    detalhe = cache.get(parcela_id) or {}
    if not detalhe:
        return item
    return _mesclar_item_receita(item, detalhe)


def _numero_fatura_item(item: dict) -> str:
    fatura = item.get('fatura')
    if isinstance(fatura, dict):
        for key in ('numero', 'numero_nota', 'numero_nf', 'rps'):
            val = fatura.get(key)
            if val is not None and str(val).strip() not in ('', '0'):
                return str(val).strip()
    for key in ('numero_nota_fiscal', 'numero_nf', 'numero_nota'):
        val = item.get(key)
        if val is not None and str(val).strip() not in ('', '0'):
            return str(val).strip()
    return ''


def _numero_venda_item(item: dict) -> str:
    evento = item.get('evento') if isinstance(item.get('evento'), dict) else {}
    codigo = str(evento.get('codigo_referencia') or item.get('codigo_referencia') or '').strip()
    if codigo:
        return codigo
    venda = item.get('venda')
    if isinstance(venda, dict):
        for key in ('numero', 'codigo', 'numero_venda'):
            val = venda.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    for key in ('numero_venda', 'codigo_venda'):
        val = item.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''


def _numero_nota_item(item: dict) -> str:
    nota = item.get('nota')
    if isinstance(nota, dict):
        for key in ('numero', 'numero_nota', 'numero_nf', 'numero_nfe', 'numero_nota_fiscal'):
            val = nota.get(key)
            if val is not None and str(val).strip() not in ('', '0'):
                return str(val).strip()
    elif nota is not None and str(nota).strip() not in ('', '0'):
        s = str(nota).strip()
        if not _RE_UUID.match(s):
            return s
    return ''


def _documento_despesa_item(item: dict) -> str:
    """Nota fiscal de entrada; sem NF permanece em branco (nunca UUID da parcela)."""
    doc = _numero_fatura_item(item)
    if doc:
        return doc[:15]
    doc = _numero_nota_item(item)
    if doc:
        return doc[:15]
    bruto = str(item.get('documento') or item.get('numero_documento') or '').strip()
    if bruto and not _RE_UUID.match(bruto):
        return bruto[:15]
    return ''


def _documento_receita_item(item: dict) -> str:
    """Nota fiscal; se não houver, número/código da venda."""
    doc = _numero_fatura_item(item)
    if doc:
        return doc[:50]
    doc = _numero_venda_item(item)
    if doc:
        return doc[:50]
    bruto = str(item.get('documento') or item.get('numero_documento') or '').strip()
    if bruto and not _RE_UUID.match(bruto):
        return bruto[:50]
    return ''


def _nsu_receita_item(item: dict) -> str:
    for key in ('nsu', 'numero_nsu', 'numero_autorizacao', 'autorizacao', 'codigo_autorizacao'):
        val = str(item.get(key) or '').strip()
        if val and not _RE_UUID.match(val):
            return val[:100]
    for baixa in reversed(item.get('baixas') or []):
        if not isinstance(baixa, dict):
            continue
        val = str(baixa.get('nsu') or baixa.get('numero_autorizacao') or '').strip()
        if val:
            return val[:100]
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


def _id_conta_financeira_item(item: dict) -> str:
    raw = item.get('conta_financeira') or item.get('conta') or item.get('conta_bancaria')
    if isinstance(raw, dict):
        return str(raw.get('id') or raw.get('uuid') or '').strip()
    return str(item.get('id_conta_financeira') or raw or '').strip()


def _documento_pessoa(item: dict) -> str:
    doc = str(
        item.get('documento')
        or item.get('cnpj')
        or item.get('cpf')
        or item.get('numero_documento')
        or ''
    ).strip()
    return ''.join(c for c in doc if c.isdigit())


def _telefone_pessoa(item: dict, *, max_len: int = 11) -> str:
    tel = str(
        item.get('telefone_celular')
        or item.get('telefone_comercial')
        or item.get('telefone')
        or ''
    ).strip()
    digits = ''.join(c for c in tel if c.isdigit())
    if not digits:
        return '0' * min(max_len, 11)
    return digits[:max_len]


def _endereco_pessoa(item: dict) -> dict:
    enderecos = item.get('enderecos') or []
    if not enderecos or not isinstance(enderecos[0], dict):
        return {}
    e = enderecos[0]
    cidade = str(e.get('cidade') or '').strip()
    uf = str(e.get('estado') or e.get('uf') or '').strip()
    cidade_uf = f'{cidade} — {uf}'.strip(' —')
    return {
        'logradouro': str(e.get('logradouro') or '')[:200],
        'numero': str(e.get('numero') or '')[:30],
        'complemento': str(e.get('complemento') or '')[:120],
        'bairro': str(e.get('bairro') or '')[:100],
        'cidade_uf': cidade_uf[:200],
        'cep': ''.join(c for c in str(e.get('cep') or '') if c.isdigit())[:15],
    }


def _codigo_externo_ca(item: dict, ca_id: str) -> str:
    codigo = str(item.get('codigo') or item.get('codigo_pessoa') or '').strip()
    if codigo:
        return codigo[:50]
    return f'CA-{ca_id}'[:50]


def importar_clientes(empresa, client: ContaAzulClient, *, dry_run: bool = False) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    try:
        itens = client.buscar_clientes()
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}
    for item in itens:
        ca_id = str(item.get('id') or item.get('uuid') or '').strip()
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        nome = str(item.get('nome') or item.get('nome_fantasia') or 'Cliente CA').strip()[:50]
        doc = _documento_pessoa(item)
        if not doc:
            doc = _cnpj_sintetico_conta_azul(empresa.pk, f'cli:{ca_id}')[:14]
        else:
            doc = doc[:14]
        telefone = _telefone_pessoa(item)
        try:
            obj = Cliente.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
            if not obj and doc:
                obj = Cliente.objects.filter(empresa=empresa, cnpj=doc).first()
            if not obj:
                obj = Cliente.objects.filter(empresa=empresa, razao__iexact=nome, conta_azul_id='').first()
            if obj:
                obj.conta_azul_id = ca_id
                obj.razao = nome
                obj.cnpj = doc
                obj.telefone = telefone
                obj.codigo_externo = _codigo_externo_ca(item, ca_id)
                obj.save()
                stats['atualizados'] += 1
            else:
                Cliente.objects.create(
                    empresa=empresa,
                    conta_azul_id=ca_id,
                    razao=nome,
                    cnpj=doc,
                    telefone=telefone,
                    codigo_externo=_codigo_externo_ca(item, ca_id),
                )
                stats['criados'] += 1
        except IntegrityError:
            stats['erros'] += 1
    return stats


def importar_fornecedores(empresa, client: ContaAzulClient, *, dry_run: bool = False) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    try:
        itens = client.buscar_fornecedores()
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}
    for item in itens:
        ca_id = str(item.get('id') or item.get('uuid') or '').strip()
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        try:
            criado = _salvar_fornecedor_pessoa(empresa, item, ca_id)
            if criado:
                stats['criados'] += 1
            else:
                stats['atualizados'] += 1
        except IntegrityError:
            stats['erros'] += 1
    return stats


def _salvar_fornecedor_pessoa(empresa, item: dict, ca_id: str) -> bool:
    """Salva/atualiza fornecedor a partir de pessoa CA. Retorna True se criou."""
    nome = str(item.get('nome') or item.get('nome_fantasia') or 'Fornecedor CA').strip()[:200]
    nome_fantasia = str(item.get('nome_fantasia') or '')[:200]
    doc = _documento_pessoa(item)
    if not doc:
        doc = _cnpj_sintetico_conta_azul(empresa.pk, f'forn:{ca_id}')
    end = _endereco_pessoa(item)
    email = str(item.get('email') or '')[:254]
    defaults = {
        'razao': nome,
        'nome_fantasia': nome_fantasia,
        'cnpj': doc[:20],
        'telefone': _telefone_pessoa(item, max_len=20),
        'conta_azul_id': ca_id,
        'codigo_externo': _codigo_externo_ca(item, ca_id),
        'endereco_eletronico': email,
        **end,
    }
    obj = Fornecedor.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
    if not obj and doc:
        obj = Fornecedor.objects.filter(empresa=empresa, cnpj=doc).first()
    if not obj:
        obj = Fornecedor.objects.filter(empresa=empresa, razao__iexact=nome, conta_azul_id='').first()
    if obj:
        for key, val in defaults.items():
            setattr(obj, key, val)
        obj.save()
        return False
    Fornecedor.objects.create(empresa=empresa, **defaults)
    return True


def _fornecedor_de_item(empresa, item: dict) -> Fornecedor | None:
    ca_id = ''
    forn_raw = item.get('fornecedor')
    if isinstance(forn_raw, dict):
        ca_id = str(forn_raw.get('id') or forn_raw.get('uuid') or '').strip()
    if not ca_id:
        ca_id = str(item.get('id_fornecedor') or item.get('fornecedor_id') or '').strip()
    if ca_id:
        obj = Fornecedor.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
        if obj:
            return obj
        obj = Fornecedor.objects.filter(empresa=empresa, codigo_externo=f'CA-{ca_id}'[:50]).first()
        if obj:
            return obj
    nome = _nome_fornecedor_item(item)
    obj = Fornecedor.objects.filter(empresa=empresa, razao__iexact=nome).first()
    if obj:
        return obj
    if ca_id:
        try:
            return Fornecedor.objects.create(
                empresa=empresa,
                razao=nome[:200],
                cnpj=_cnpj_sintetico_conta_azul(empresa.pk, f'forn:{ca_id}'),
                conta_azul_id=ca_id,
                codigo_externo=f'CA-{ca_id}'[:50],
            )
        except IntegrityError:
            return Fornecedor.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
    cnpj_api = _documento_pessoa(item if isinstance(forn_raw, dict) else {'documento': item.get('documento_fornecedor')})
    if cnpj_api and len(cnpj_api) >= 11:
        obj = Fornecedor.objects.filter(empresa=empresa, cnpj=cnpj_api).first()
        if obj:
            return obj
        try:
            return Fornecedor.objects.create(
                empresa=empresa,
                razao=nome[:200],
                cnpj=cnpj_api[:20],
                conta_azul_id=ca_id,
                codigo_externo=f'CA-{ca_id}'[:50] if ca_id else '',
            )
        except IntegrityError:
            return Fornecedor.objects.filter(empresa=empresa, cnpj=cnpj_api).first()
    cnpj = _cnpj_sintetico_conta_azul(empresa.pk, ca_id or nome)
    obj = Fornecedor.objects.filter(empresa=empresa, cnpj=cnpj).first()
    if obj:
        return obj
    try:
        return Fornecedor.objects.create(
            empresa=empresa,
            razao=nome[:200],
            cnpj=cnpj,
            conta_azul_id=ca_id,
            codigo_externo=f'CA-{ca_id}'[:50] if ca_id else '',
        )
    except IntegrityError:
        return Fornecedor.objects.filter(empresa=empresa, cnpj=cnpj).first()


def _banco_de_item(item: dict) -> Banco:
    codigo = str(item.get('codigo_banco') or '').strip()
    nome_banco = str(item.get('banco') or 'OUTROS').replace('_', ' ').title()
    if codigo:
        b = Banco.objects.filter(codigo=codigo).first()
        if b:
            return b
        return Banco.objects.create(codigo=codigo, nome=nome_banco[:120])
    b = Banco.objects.filter(nome__iexact=nome_banco).first()
    if b:
        return b
    return Banco.objects.create(nome=nome_banco[:120], codigo=codigo or '')


def _extrair_saldo_ca(dados) -> Decimal | None:
    if dados is None:
        return None
    if isinstance(dados, (int, float, str)):
        return _parse_decimal(dados)
    if not isinstance(dados, dict):
        return None
    for key in ('saldo_atual', 'saldo', 'valor', 'total', 'saldo_disponivel'):
        if key in dados and dados[key] is not None and dados[key] != '':
            return _parse_decimal(dados[key])
    for key in ('saldo_atual', 'saldo', 'dados'):
        nested = dados.get(key)
        if isinstance(nested, dict):
            saldo = _extrair_saldo_ca(nested)
            if saldo is not None:
                return saldo
    return None


def _gravar_saldo_conta_azul(conta: ContaBancaria, saldo: Decimal) -> None:
    conta.saldo_conta_azul = saldo
    conta.saldo_conta_azul_em = timezone.now()
    conta.save(update_fields=['saldo_conta_azul', 'saldo_conta_azul_em'])


def _atualizar_saldo_conta_api(conta: ContaBancaria, client: ContaAzulClient) -> bool:
    if not conta.conta_azul_id:
        return False
    try:
        payload = client.buscar_saldo_atual_conta(conta.conta_azul_id)
    except ContaAzulAPIError:
        return False
    saldo = _extrair_saldo_ca(payload)
    if saldo is None:
        return False
    _gravar_saldo_conta_azul(conta, saldo)
    return True


def importar_saldos_contas(empresa, client: ContaAzulClient, *, dry_run: bool = False) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    contas = ContaBancaria.objects.filter(empresa=empresa).exclude(conta_azul_id='')
    for conta in contas:
        if dry_run:
            stats['atualizados'] += 1
            continue
        if _atualizar_saldo_conta_api(conta, client):
            stats['atualizados'] += 1
        else:
            stats['erros'] += 1
    return stats


def _upsert_conta_bancaria(
    empresa,
    item: dict,
    *,
    dry_run: bool = False,
    client: ContaAzulClient | None = None,
) -> tuple[bool, bool]:
    """Retorna (criado, ok). ok=False se ignorado por erro."""
    ca_id = str(item.get('id') or '').strip()
    if not ca_id:
        return False, False
    banco = _banco_de_item(item)
    agencia = str(item.get('agencia') or '').strip()[:20] or ''
    conta_num = str(item.get('numero') or item.get('conta') or '').strip()[:30] or ''
    if not conta_num:
        conta_num = f'CA-{ca_id[:12]}'
    tipo = TIPO_CONTA_MAP.get(str(item.get('tipo') or ''), 'CONTA_CORRENTE')
    defaults = {
        'banco': banco,
        'agencia': agencia or None,
        'conta': conta_num,
        'descricao': str(item.get('nome') or item.get('descricao') or f'Conta CA {ca_id[:8]}')[:200],
        'tipo': tipo,
        'status': 'A' if item.get('ativo', True) else 'I',
        'conta_azul_id': ca_id,
    }
    if dry_run:
        return True, True

    obj = ContaBancaria.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
    if not obj:
        obj = ContaBancaria.objects.filter(
            empresa=empresa,
            banco=banco,
            agencia=defaults['agencia'],
            conta=defaults['conta'],
        ).first()
    if not obj:
        desc = defaults['descricao']
        obj = ContaBancaria.objects.filter(
            empresa=empresa,
            conta_azul_id='',
            descricao__iexact=desc,
        ).first()

    if obj:
        for key, val in defaults.items():
            setattr(obj, key, val)
        try:
            obj.save()
        except IntegrityError:
            obj.conta = f'{conta_num}-{ca_id[:6]}'
            obj.save()
        _aplicar_saldo_conta_item(obj, item, client)
        return False, True

    try:
        obj = ContaBancaria.objects.create(empresa=empresa, **defaults)
        _aplicar_saldo_conta_item(obj, item, client)
        return True, True
    except IntegrityError:
        obj = ContaBancaria.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
        if obj:
            _aplicar_saldo_conta_item(obj, item, client)
            return False, True
        defaults['conta'] = f'{conta_num}-{ca_id[:6]}'
        obj = ContaBancaria.objects.create(empresa=empresa, **defaults)
        _aplicar_saldo_conta_item(obj, item, client)
        return True, True


def _aplicar_saldo_conta_item(
    conta: ContaBancaria,
    item: dict,
    client: ContaAzulClient | None,
) -> None:
    saldo = _extrair_saldo_ca(item)
    if saldo is not None:
        _gravar_saldo_conta_azul(conta, saldo)
        return
    if client and conta.conta_azul_id:
        _atualizar_saldo_conta_api(conta, client)


def _id_categoria_ca(item: dict) -> str:
    return str(item.get('id') or item.get('uuid') or '').strip()


def _id_pai_categoria_ca(item: dict) -> str:
    pai = item.get('categoria_pai')
    if isinstance(pai, dict):
        return str(pai.get('id') or pai.get('uuid') or '').strip()
    return str(pai or '').strip()


def _rotulo_categoria_ca(item: dict) -> str:
    """Nome exibido no Conta Azul (já inclui código quando aplicável)."""
    nome = str(item.get('nome') or item.get('descricao') or '').strip()
    codigo = str(item.get('codigo') or '').strip()
    if codigo and nome and not nome.startswith(codigo):
        return f'{codigo} - {nome}'[:100]
    return (nome or codigo)[:100]


def _grupo_categoria_ca(item: dict, por_id: dict[str, dict]) -> str:
    """Grupo = nome da categoria pai ('Aparecer dentro da categoria' no CA)."""
    pai_id = _id_pai_categoria_ca(item)
    if pai_id:
        pai = por_id.get(pai_id) or por_id.get(pai_id.lower())
        if pai:
            return _rotulo_categoria_ca(pai)
    pai_raw = item.get('categoria_pai')
    if isinstance(pai_raw, dict):
        return _rotulo_categoria_ca(pai_raw)
    return ''


def _tipo_categoria_ca(item: dict) -> str:
    tipo_api = str(item.get('tipo') or '').upper()
    return 'R' if tipo_api == 'RECEITA' else 'D'


def importar_categorias(empresa, client: ContaAzulClient, *, dry_run: bool = False) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'grupos': 0, 'preservadas': 0, 'erros': 0}
    try:
        itens = client.buscar_categorias(apenas_filhos=False)
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}

    por_id = {_id_categoria_ca(i): i for i in itens if _id_categoria_ca(i)}
    por_id.update({k.lower(): v for k, v in por_id.items()})
    pais_com_filhos: set[str] = set()
    for item in itens:
        pai_id = _id_pai_categoria_ca(item)
        if pai_id:
            pais_com_filhos.add(pai_id)
            pais_com_filhos.add(pai_id.lower())

    for item in itens:
        ca_id = _id_categoria_ca(item)
        nome = str(item.get('nome') or item.get('descricao') or 'Sem nome')[:100]
        tipo = _tipo_categoria_ca(item)
        grupo = _grupo_categoria_ca(item, por_id)
        sintetico = 'S' if ca_id in pais_com_filhos or ca_id.lower() in pais_com_filhos else 'A'
        codigo = str(item.get('codigo') or '').strip()[:30]
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            if grupo:
                stats['grupos'] += 1
            continue
        try:
            obj = Categoria.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
            if not obj:
                obj = Categoria.objects.filter(
                    empresa=empresa,
                    nome__iexact=nome,
                    tipo=tipo,
                ).filter(conta_azul_id='').first()
            if obj and obj.bloquear_sync_conta_azul:
                stats['preservadas'] += 1
                continue
            if obj:
                obj.conta_azul_id = ca_id
                obj.nome = nome
                if tipo in ('R', 'D'):
                    obj.tipo = tipo
                obj.classificacao = codigo or obj.classificacao or nome[:30]
                obj.sintetico = sintetico
                if grupo:
                    if obj.grupo != grupo:
                        stats['grupos'] += 1
                    obj.grupo = grupo
                obj.save()
                stats['atualizados'] += 1
            else:
                Categoria.objects.create(
                    empresa=empresa,
                    conta_azul_id=ca_id,
                    nome=nome,
                    tipo=tipo,
                    grupo=grupo or None,
                    classificacao=codigo or nome[:30],
                    sintetico=sintetico,
                )
                stats['criados'] += 1
                if grupo:
                    stats['grupos'] += 1
        except IntegrityError:
            stats['erros'] += 1
    return stats


def importar_centros_custo(empresa, client: ContaAzulClient, *, dry_run: bool = False) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    try:
        itens = client.buscar_centros_custo()
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}
    for item in itens:
        ca_id = str(item.get('id') or '').strip()
        nome = str(item.get('nome') or 'Centro')[:200]
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        _, created = CentroCusto.objects.update_or_create(
            empresa=empresa,
            conta_azul_id=ca_id,
            defaults={
                'nome': nome,
                'ativo': bool(item.get('ativo', True)),
                'codigo': str(item.get('codigo') or '')[:60],
            },
        )
        stats['criados' if created else 'atualizados'] += 1
    return stats


def importar_contas_financeiras(empresa, client: ContaAzulClient, *, dry_run: bool = False) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    try:
        itens = client.buscar_contas_financeiras()
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}
    for item in itens:
        ca_id = str(item.get('id') or '').strip()
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        try:
            criado, ok = _upsert_conta_bancaria(empresa, item, dry_run=dry_run, client=client)
            if not ok:
                stats['erros'] += 1
            elif criado:
                stats['criados'] += 1
            else:
                stats['atualizados'] += 1
        except IntegrityError:
            stats['erros'] += 1
    if not dry_run:
        saldos = importar_saldos_contas(empresa, client, dry_run=False)
        stats['saldos_atualizados'] = saldos.get('atualizados', 0)
        stats['saldos_erros'] = saldos.get('erros', 0)
    return stats


def _categoria_por_ca(empresa, ca_id: str):
    if not ca_id:
        return None
    cat = Categoria.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
    if cat:
        return cat
    return Categoria.objects.filter(empresa=empresa, conta_azul_id__iexact=ca_id.strip()).first()


def _conta_por_ca(empresa, ca_id: str):
    if not ca_id:
        return None
    return ContaBancaria.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()


def importar_receitas(
    empresa,
    client: ContaAzulClient,
    *,
    data_de: date,
    data_ate: date,
    dry_run: bool = False,
) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    params = {
        'pagina': 1,
        'tamanho_pagina': 100,
        'data_vencimento_de': data_de.isoformat(),
        'data_vencimento_ate': data_ate.isoformat(),
    }
    try:
        itens = client.buscar_receitas(**params)
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}
    cache_parcelas: dict[str, dict] = {}
    cache_cobranca: dict[str, Cobranca] = {}
    cache_categorias: dict[str, Categoria | None] = {}
    cache_contas: dict[str, ContaBancaria | None] = {}
    chamadas_detalhe = 0
    preparados: list[tuple[str, dict]] = []
    for item in itens:
        parcela_id = str(item.get('id') or item.get('id_parcela') or '').strip()
        if not parcela_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        item = _aplicar_campos_da_descricao(item)
        if _precisa_detalhe_parcela(item):
            if parcela_id not in cache_parcelas:
                if chamadas_detalhe < LIMITE_DETALHE_PARCELA_SYNC:
                    chamadas_detalhe += 1
                    item = _enriquecer_item_receita(client, item, cache_parcelas)
            else:
                item = _enriquecer_item_receita(client, item, cache_parcelas)
        status_local = _map_status_receita(item)
        cat_id = ''
        cats = item.get('categorias') or []
        if cats and isinstance(cats[0], dict):
            cat_id = str(cats[0].get('id') or '')
        valor = _parse_decimal(item.get('valor') or item.get('total') or item.get('valor_liquido'))
        valor_pago = _valor_pago_item(item)
        data_pg = _data_pagamento_item(item, data_de)
        if cat_id not in cache_categorias:
            cache_categorias[cat_id] = _categoria_por_ca(empresa, cat_id)
        conta_ca_id = _id_conta_financeira_item(item)
        if conta_ca_id not in cache_contas:
            cache_contas[conta_ca_id] = _conta_por_ca(empresa, conta_ca_id)
        preparados.append((
            parcela_id,
            {
                'cliente': _nome_cliente_item(empresa, item),
                'data_vencimento': _parse_data(item.get('data_vencimento')) or data_de,
                'data_emissao': _parse_data(item.get('data_competencia')) or data_de,
                'valor_a_receber': valor,
                'valor_recebido': valor_pago if status_local == 'pago' else Decimal('0'),
                'data_recebimento': data_pg,
                'status': status_local,
                'doc': _documento_receita_item(item),
                'autorizacao': _nsu_receita_item(item),
                'observacao': str(item.get('descricao') or item.get('observacao') or '')[:500],
                'categoria': cache_categorias[cat_id],
                'conta_banco': cache_contas[conta_ca_id],
                'forma_pagamento': _cobranca_de_item(item, cache_cobranca),
            },
        ))

    if preparados and not dry_run:
        ids = [p[0] for p in preparados]
        existentes = {
            c.conta_azul_parcela_id: c
            for c in ContaAReceber.objects.filter(
                empresa=empresa,
                conta_azul_parcela_id__in=ids,
            )
        }
        campos_update = (
            'cliente', 'data_vencimento', 'data_emissao', 'valor_a_receber',
            'valor_recebido', 'data_recebimento', 'status', 'doc', 'autorizacao',
            'observacao', 'categoria', 'conta_banco', 'forma_pagamento',
        )
        criar: list[ContaAReceber] = []
        atualizar: list[ContaAReceber] = []
        for parcela_id, defaults in preparados:
            obj = existentes.get(parcela_id)
            if obj:
                for campo, val in defaults.items():
                    setattr(obj, campo, val)
                atualizar.append(obj)
            else:
                criar.append(ContaAReceber(
                    empresa=empresa,
                    conta_azul_parcela_id=parcela_id,
                    **defaults,
                ))
        try:
            if criar:
                ContaAReceber.objects.bulk_create(criar, batch_size=300)
                stats['criados'] += len(criar)
            if atualizar:
                ContaAReceber.objects.bulk_update(atualizar, campos_update, batch_size=300)
                stats['atualizados'] += len(atualizar)
        except IntegrityError:
            stats['erros'] += len(preparados)
    if chamadas_detalhe >= LIMITE_DETALHE_PARCELA_SYNC:
        stats['detalhes_limitados'] = chamadas_detalhe
    return stats


def importar_despesas(
    empresa,
    client: ContaAzulClient,
    *,
    data_de: date,
    data_ate: date,
    dry_run: bool = False,
) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    cobranca_padrao = _cobranca_padrao()
    params = {
        'pagina': 1,
        'tamanho_pagina': 100,
        'data_vencimento_de': data_de.isoformat(),
        'data_vencimento_ate': data_ate.isoformat(),
    }
    try:
        itens = client.buscar_despesas(**params)
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}

    categoria_fallback = Categoria.objects.filter(empresa=empresa, tipo='D').first()
    conta_fallback = ContaBancaria.objects.filter(empresa=empresa).first()
    cache_categorias: dict[str, Categoria | None] = {}
    cache_contas: dict[str, ContaBancaria | None] = {}
    cache_cobranca: dict[str, Cobranca] = {}
    cache_fornecedores: dict[str, Fornecedor | None] = {}
    cache_parcelas: dict[str, dict] = {}
    chamadas_detalhe = 0
    preparados: list[tuple[str, dict]] = []

    for item in itens:
        parcela_id = str(item.get('id') or item.get('id_parcela') or '').strip()
        if not parcela_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue

        forn_key = ''
        forn_raw = item.get('fornecedor')
        if isinstance(forn_raw, dict):
            forn_key = str(forn_raw.get('id') or forn_raw.get('uuid') or '').strip()
        if not forn_key:
            forn_key = str(item.get('id_fornecedor') or item.get('fornecedor_id') or _nome_fornecedor_item(item)).strip()
        if forn_key not in cache_fornecedores:
            cache_fornecedores[forn_key] = _fornecedor_de_item(empresa, item)
        fornecedor = cache_fornecedores[forn_key]
        if not fornecedor:
            stats['erros'] += 1
            continue

        cat_id = ''
        cats = item.get('categorias') or []
        if cats and isinstance(cats[0], dict):
            cat_id = str(cats[0].get('id') or '')
        if cat_id not in cache_categorias:
            cache_categorias[cat_id] = _categoria_por_ca(empresa, cat_id)
        categoria = cache_categorias[cat_id] or categoria_fallback
        if not categoria:
            categoria = Categoria.objects.create(
                empresa=empresa,
                nome='Despesa Conta Azul',
                tipo='D',
                classificacao='CA',
                sintetico='A',
            )
            cache_categorias[cat_id] = categoria

        conta_ca_id = _id_conta_financeira_item(item)
        if conta_ca_id not in cache_contas:
            cache_contas[conta_ca_id] = _conta_por_ca(empresa, conta_ca_id)
        conta = cache_contas[conta_ca_id] or conta_fallback
        if not conta:
            stats['erros'] += 1
            continue

        item = _aplicar_campos_da_descricao(item)
        if not _documento_despesa_item(item):
            if parcela_id not in cache_parcelas:
                if chamadas_detalhe < LIMITE_DETALHE_PARCELA_SYNC:
                    chamadas_detalhe += 1
                    item = _enriquecer_item_receita(client, item, cache_parcelas)
            else:
                item = _enriquecer_item_receita(client, item, cache_parcelas)
        status_local = _map_status_despesa(item)
        valor = _parse_decimal(item.get('valor') or item.get('total'))
        valor_pago = _valor_pago_item(item)
        data_pg = _data_pagamento_item(item, data_de)
        cobranca = _cobranca_de_item(item, cache_cobranca) or cobranca_padrao
        numdoc = _documento_despesa_item(item)
        preparados.append((
            parcela_id,
            {
                'fornecedor': fornecedor,
                'descricao': str(item.get('descricao') or fornecedor.razao)[:100],
                'numdoc': numdoc[:15],
                'valorDoc': valor,
                'categoria': categoria,
                'parcela': '1',
                'dtvenc': _parse_data(item.get('data_vencimento')) or data_de,
                'dtEmissao': _parse_data(item.get('data_competencia')) or data_de,
                'cobranca': cobranca,
                'conta_banco': conta,
                'dtPag': data_pg,
                'valorPago': valor_pago if status_local == 'pago' else Decimal('0'),
                'status': status_local,
                'obs': 'Importado Conta Azul',
                'nossonumero': '',
                'nsu': _nsu_receita_item(item)[:15],
            },
        ))

    if preparados and not dry_run:
        ids = [p[0] for p in preparados]
        existentes = {
            c.conta_azul_parcela_id: c
            for c in ContasaPagar.objects.filter(
                empresa=empresa,
                conta_azul_parcela_id__in=ids,
            )
        }
        campos_update = (
            'fornecedor', 'descricao', 'numdoc', 'valorDoc', 'categoria', 'parcela',
            'dtvenc', 'dtEmissao', 'cobranca', 'conta_banco', 'dtPag', 'valorPago',
            'status', 'obs', 'nossonumero', 'nsu',
        )
        criar: list[ContasaPagar] = []
        atualizar: list[ContasaPagar] = []
        for parcela_id, defaults in preparados:
            obj = existentes.get(parcela_id)
            if obj:
                for campo, val in defaults.items():
                    setattr(obj, campo, val)
                atualizar.append(obj)
            else:
                criar.append(ContasaPagar(
                    empresa=empresa,
                    conta_azul_parcela_id=parcela_id,
                    **defaults,
                ))
        try:
            if criar:
                ContasaPagar.objects.bulk_create(criar, batch_size=300)
                stats['criados'] += len(criar)
            if atualizar:
                ContasaPagar.objects.bulk_update(atualizar, campos_update, batch_size=300)
                stats['atualizados'] += len(atualizar)
        except IntegrityError:
            stats['erros'] += len(preparados)
    if chamadas_detalhe >= LIMITE_DETALHE_PARCELA_SYNC:
        stats['detalhes_limitados'] = chamadas_detalhe
    return stats


def _id_conta_origem_transferencia(item: dict) -> str:
    origem = item.get('origem') if isinstance(item.get('origem'), dict) else {}
    conta_fin = origem.get('conta_financeira') if isinstance(origem.get('conta_financeira'), dict) else {}
    val = conta_fin.get('id')
    if val:
        return str(val).strip()
    conta_origem = item.get('conta_origem')
    if isinstance(conta_origem, dict) and conta_origem.get('id'):
        return str(conta_origem['id']).strip()
    if item.get('id_conta_origem'):
        return str(item['id_conta_origem']).strip()
    return ''


def importar_transferencias(
    empresa,
    client: ContaAzulClient,
    *,
    data_de: date,
    data_ate: date,
    dry_run: bool = False,
) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    params = {
        'pagina': 1,
        'tamanho_pagina': 100,
        'data_de': data_de.isoformat(),
        'data_ate': data_ate.isoformat(),
    }
    try:
        itens = client.buscar_transferencias(**params)
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}
    cache_contas: dict[str, ContaBancaria | None] = {}
    for item in itens:
        ca_id = str(item.get('id') or '').strip()
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        origem = item.get('origem') if isinstance(item.get('origem'), dict) else {}
        id_conta = _id_conta_origem_transferencia(item)
        if id_conta not in cache_contas:
            cache_contas[id_conta] = _conta_por_ca(empresa, id_conta)
        conta_origem = cache_contas[id_conta]
        if not conta_origem:
            stats['erros'] += 1
            continue
        valor = _parse_decimal(item.get('valor'))
        dia = _parse_data(item.get('data') or origem.get('data') or item.get('data_transferencia')) or data_de
        desc = str(item.get('descricao') or 'Transferência Conta Azul')[:255]
        hash_unico = f'ca-transfer-{ca_id}'
        defaults = {
            'banco': conta_origem.banco,
            'data': dia,
            'historico': desc,
            'valor': -abs(valor),
            'origem': 'CONTA_AZUL',
            'hash_unico': hash_unico,
            'documento': ca_id[:60],
        }
        try:
            _, created = Lancamento.objects.update_or_create(
                empresa=empresa,
                conta=conta_origem,
                hash_unico=hash_unico,
                defaults=defaults,
            )
            stats['criados' if created else 'atualizados'] += 1
        except IntegrityError:
            stats['erros'] += 1
    return stats


def sincronizar_conta_azul(
    empresa,
    *,
    cadastros: bool = False,
    receitas: bool = False,
    despesas: bool = False,
    transferencias: bool = False,
    data_de: date | None = None,
    data_ate: date | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    def _rodar() -> dict[str, Any]:
        client = ContaAzulClient.para_empresa(empresa)
        resultado: dict[str, Any] = {}
        if cadastros:
            resultado['categorias'] = importar_categorias(empresa, client, dry_run=dry_run)
            resultado['centros_custo'] = importar_centros_custo(empresa, client, dry_run=dry_run)
            resultado['contas'] = importar_contas_financeiras(empresa, client, dry_run=dry_run)
            resultado['clientes'] = importar_clientes(empresa, client, dry_run=dry_run)
            resultado['fornecedores'] = importar_fornecedores(empresa, client, dry_run=dry_run)
        if data_de and data_ate:
            if receitas:
                resultado['receitas'] = importar_receitas(
                    empresa, client, data_de=data_de, data_ate=data_ate, dry_run=dry_run,
                )
            if despesas:
                resultado['despesas'] = importar_despesas(
                    empresa, client, data_de=data_de, data_ate=data_ate, dry_run=dry_run,
                )
            if transferencias:
                resultado['transferencias'] = importar_transferencias(
                    empresa, client, data_de=data_de, data_ate=data_ate, dry_run=dry_run,
                )
        cfg = getattr(empresa, 'conta_azul_config', None)
        if cfg and not dry_run:
            cfg.save(update_fields=['atualizado_em'])
        return resultado

    return _com_retry_sqlite(_rodar)


def mensagem_resultado_sync(resultado: dict[str, Any]) -> tuple[str, str]:
    """Retorna (nível Django messages, texto legível). nível: success | warning | error."""
    if not resultado:
        return 'warning', 'Nenhuma opção de sincronização foi selecionada.'

    erros: list[str] = []
    ok: list[str] = []
    for chave, stats in resultado.items():
        if not isinstance(stats, dict):
            continue
        if stats.get('erro'):
            erros.append(str(stats['erro']))
            continue
        criados = stats.get('criados', 0)
        atualizados = stats.get('atualizados', 0)
        erros_qtd = stats.get('erros', 0)
        rotulo = chave.replace('_', ' ')
        ok.append(f'{rotulo}: {criados} criados, {atualizados} atualizados')
        if stats.get('grupos'):
            ok[-1] += f', {stats["grupos"]} grupos'
        if stats.get('preservadas'):
            ok[-1] += f', {stats["preservadas"]} preservadas'
        if stats.get('saldos_atualizados'):
            ok[-1] += f', {stats["saldos_atualizados"]} saldos CA'
        if stats.get('saldos_erros'):
            ok[-1] += f', {stats["saldos_erros"]} saldos sem resposta'
        if erros_qtd:
            ok[-1] += f', {erros_qtd} ignorados'
        if stats.get('detalhes_limitados'):
            ok[-1] += f' (detalhe API limitado a {stats["detalhes_limitados"]} parcelas; rode de novo para completar NSU/cobrança)'

    erros_unicos = list(dict.fromkeys(erros))
    if erros_unicos and not ok:
        msg = erros_unicos[0] if len(erros_unicos) == 1 else '; '.join(erros_unicos)
        return 'error', msg
    if erros_unicos:
        return 'warning', f'Parcialmente sincronizado ({"; ".join(ok)}). Erros: {erros_unicos[0]}'
    return 'success', f'Sincronização concluída: {"; ".join(ok)}'
