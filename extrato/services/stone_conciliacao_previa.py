"""Sugestões de conciliação Stone na prévia do extrato (estilo Concilflex)."""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta
from decimal import Decimal
from itertools import combinations
from typing import Any

from django.db import transaction

from contasareceber.models import BaixaContaAReceber
from extrato.models import ExtratoMovimento, Lancamento
from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

TOLERANCIA_VALOR = Decimal('0.10')
JANELA_DIAS = 3
MAX_COMBO = 12

_RE_STONE_HIST = re.compile(
    r'recebimento\s+vendas\s*-\s*(?P<bandeira>.+?)\s*\|\s*(?P<tipo>.+?)\s*$',
    re.IGNORECASE,
)


def _normalizar(texto: str) -> str:
    if not texto:
        return ''
    t = unicodedata.normalize('NFD', (texto or '').lower())
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn').strip()


def _tipo_cartao_do_historico(tipo_raw: str) -> str | None:
    t = _normalizar(tipo_raw)
    if 'debit' in t or 'debito' in t:
        return 'debito'
    if 'credit' in t or 'credito' in t:
        return 'credito'
    return None


def _bandeiras_compat(a: str, b: str) -> bool:
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    aliases = {
        'americanexpress': {'amex', 'americanexpress', 'american express'},
        'mastercard': {'mastercard', 'master', 'maestro'},
        'visa': {'visa'},
        'elo': {'elo'},
        'hipercard': {'hipercard', 'hiper'},
    }
    for grupo in aliases.values():
        if na in grupo and nb in grupo:
            return True
    return False


def _forma_bate_tipo(forma_pagamento: str, tipo: str | None) -> bool:
    if not tipo:
        return True
    fp = _normalizar(forma_pagamento or '')
    if tipo == 'debito':
        return 'debit' in fp or 'debito' in fp
    if tipo == 'credito':
        return 'credit' in fp or 'credito' in fp
    return True


def parse_stone_historico(historico: str) -> dict[str, str] | None:
    """Extrai bandeira e tipo de histórico Stone: Recebimento vendas - Elo | Crédito."""
    hist = (historico or '').strip()
    if not hist:
        return None
    m = _RE_STONE_HIST.search(hist)
    if not m:
        return None
    tipo = _tipo_cartao_do_historico(m.group('tipo'))
    return {
        'bandeira': (m.group('bandeira') or '').strip(),
        'tipo': tipo or '',
    }


def eh_lancamento_stone(lancamento: Lancamento) -> bool:
    if parse_stone_historico(lancamento.historico or ''):
        return True
    conta = lancamento.conta
    if conta and (conta.nome_curto() or '').upper() == 'STONE':
        return True
    return 'recebimento vendas' in _normalizar(lancamento.historico or '')


def _serializar_relatorio(rel: RelatorioRecebiveisMaquinaCartao) -> dict[str, Any]:
    nota_num = rel.nota_fiscal or ''
    autorizacao = rel.numero_autorizacao or ''
    cliente = rel.razao or ''
    if rel.conta_a_receber_id:
        car = rel.conta_a_receber
        nota_num = nota_num or (car.doc or '')
        autorizacao = autorizacao or (car.autorizacao or '')
        cliente = cliente or (car.cliente or '')
        if car.nota_id:
            nota_num = nota_num or str(car.nota.numero_nota or '')
            autorizacao = autorizacao or (car.nota.nsu or '')
    return {
        'id': rel.id,
        'valor_liquido': rel.valor_liquido,
        'bandeira': rel.bandeira or '',
        'forma_pagamento': rel.forma_pagamento or '',
        'data_pagamento': rel.data_pagamento,
        'nota_fiscal': nota_num,
        'autorizacao': autorizacao,
        'cliente': cliente,
        'parcela': f'{rel.parcelas}/{rel.total_parcelas}',
    }


def _candidatos_stone(lancamento: Lancamento, empresa_id: int, parsed: dict) -> list[RelatorioRecebiveisMaquinaCartao]:
    if not lancamento.data or lancamento.valor <= 0:
        return []
    data_ini = lancamento.data - timedelta(days=JANELA_DIAS)
    data_fim = lancamento.data + timedelta(days=JANELA_DIAS)
    qs = (
        RelatorioRecebiveisMaquinaCartao.objects.filter(
            empresa_id=empresa_id,
            conciliado=False,
            maquinha='STONE',
            data_pagamento__range=(data_ini, data_fim),
        )
        .select_related('conta_a_receber', 'conta_a_receber__nota')
        .order_by('data_pagamento', 'valor_liquido')
    )
    candidatos = []
    for rel in qs:
        if not _bandeiras_compat(parsed.get('bandeira', ''), rel.bandeira or ''):
            continue
        if not _forma_bate_tipo(rel.forma_pagamento or '', parsed.get('tipo') or None):
            continue
        candidatos.append(rel)
    return candidatos


def _buscar_combinacao(
    valor_alvo: Decimal,
    candidatos: list[RelatorioRecebiveisMaquinaCartao],
) -> list[RelatorioRecebiveisMaquinaCartao] | None:
    if not candidatos:
        return None
    for rel in candidatos:
        if abs(rel.valor_liquido - valor_alvo) <= TOLERANCIA_VALOR:
            return [rel]
    limite = min(len(candidatos), MAX_COMBO)
    subset = candidatos[:limite]
    for n in range(2, len(subset) + 1):
        for combo in combinations(subset, n):
            soma = sum(r.valor_liquido for r in combo)
            if abs(soma - valor_alvo) <= TOLERANCIA_VALOR:
                return list(combo)
    return None


def sugerir_conciliacao_stone(lancamento: Lancamento, empresa_id: int) -> dict[str, Any] | None:
    """Retorna sugestão de conciliação para um lançamento Stone na prévia."""
    if lancamento.conciliado or lancamento.valor <= 0:
        return None
    if not eh_lancamento_stone(lancamento):
        return None

    parsed = parse_stone_historico(lancamento.historico or '') or {
        'bandeira': '',
        'tipo': '',
    }
    candidatos = _candidatos_stone(lancamento, empresa_id, parsed)
    combo = _buscar_combinacao(lancamento.valor, candidatos)
    if not combo:
        return {
            'eh_stone': True,
            'bandeira': parsed.get('bandeira', ''),
            'tipo': parsed.get('tipo', ''),
            'confianca': 'nenhuma',
            'relatorio_ids': [],
            'soma_liquida': Decimal('0'),
            'itens': [],
            'mensagem': 'Nenhum recebível Stone compatível encontrado. Importe o CSV Stone ou ajuste data/bandeira.',
        }

    soma = sum(r.valor_liquido for r in combo)
    confianca = 'alta' if len(combo) == 1 and abs(soma - lancamento.valor) <= Decimal('0.01') else 'media'
    return {
        'eh_stone': True,
        'bandeira': parsed.get('bandeira', ''),
        'tipo': parsed.get('tipo', ''),
        'confianca': confianca,
        'relatorio_ids': [r.id for r in combo],
        'soma_liquida': soma,
        'itens': [_serializar_relatorio(r) for r in combo],
        'mensagem': '',
    }


def conciliar_stone_lancamento(
    lancamento: Lancamento,
    relatorio_ids: list[int],
    empresa_id: int,
) -> int:
    """Concilia lançamento (prévia ou importado) com recebíveis Stone. Retorna qtd movimentos criados."""
    if lancamento.empresa_id != empresa_id:
        raise ValueError('Lançamento não pertence à empresa.')
    if lancamento.conciliado:
        raise ValueError('Lançamento já conciliado.')

    relatorios = list(
        RelatorioRecebiveisMaquinaCartao.objects.filter(
            id__in=relatorio_ids,
            empresa_id=empresa_id,
            conciliado=False,
            maquinha='STONE',
        ).select_related('conta_a_receber')
    )
    if not relatorios:
        raise ValueError('Nenhum recebível Stone elegível.')

    soma = sum(r.valor_liquido for r in relatorios)
    if abs(soma - lancamento.valor) > TOLERANCIA_VALOR:
        raise ValueError(
            f'Soma dos recebíveis (R$ {soma:.2f}) difere do lançamento (R$ {lancamento.valor:.2f}).'
        )

    movimentos = 0
    with transaction.atomic():
        for relatorio in relatorios:
            descricao = (
                f'{lancamento.historico} {relatorio.nota_fiscal or ""} '
                f'{relatorio.parcelas}/{relatorio.total_parcelas} - {relatorio.razao or ""} '
                f'- R$ {relatorio.valor_liquido:.2f}'
            )
            movimento = ExtratoMovimento.objects.create(
                empresa_id=empresa_id,
                data_baixa=lancamento.data,
                descricao=descricao.strip(),
                valor=relatorio.valor_liquido,
                situacao='recebido',
                conta_banco=lancamento.conta,
                lancamento=lancamento,
                conta_receber=relatorio.conta_a_receber,
                saldo=0,
            )
            relatorio.conciliado = True
            relatorio.identificacao_extrato = str(lancamento.fitid or lancamento.pk)
            relatorio.save(update_fields=['conciliado', 'identificacao_extrato'])

            if relatorio.conta_a_receber_id:
                conta = relatorio.conta_a_receber
                conta.status = 'pago'
                conta.data_recebimento = lancamento.data
                conta.valor_recebido = relatorio.valor_bruto or relatorio.valor_liquido
                conta.save()

                baixa = BaixaContaAReceber.objects.create(
                    conta_a_receber=conta,
                    empresa_id=empresa_id,
                    valor_recebido=relatorio.valor_liquido,
                    data_recebimento=lancamento.data,
                    conta_banco=lancamento.conta,
                )
                movimento.baixa_receber = baixa
                movimento.save(update_fields=['baixa_receber'])

            movimentos += 1

        lancamento.conciliado = True
        hist = lancamento.historico or ''
        ids_txt = ', '.join(str(r.id) for r in relatorios)
        if 'Relatórios:' not in hist:
            lancamento.historico = f'{hist} - Relatórios: {ids_txt}'.strip(' -')
        lancamento.save(update_fields=['conciliado', 'historico'])

    return movimentos
