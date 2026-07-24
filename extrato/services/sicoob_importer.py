"""Converte JSON de extrato Sicoob em lançamentos do modelo extrato.Lancamento."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser as date_parser
from django.db import IntegrityError, transaction

from ..models import ContaBancaria, Lancamento
from .ofx_importer import hash_lancamento

logger = logging.getLogger(__name__)


def _parse_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip()
    if not s:
        return Decimal("0")
    if re.match(r"^-?\d+$", s):
        return Decimal(s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def _parse_data(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    if not s:
        return None
    try:
        # ISO 8601 típico da API Sicoob: 2025-12-31T11:19
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return date_parser.parse(s, dayfirst=False).date()
        return date_parser.parse(s, dayfirst=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def extrair_transacoes_payload_sicoob(payload: Any) -> list[dict[str, Any]]:
    """
    Localiza a lista de movimentos no JSON do extrato Sicoob (estrutura varia por versão/portal).
    Aceita: ``transacoes``, ``data`` (lista), lista na raiz, ou objeto aninhado com lista de dicts
    contendo ``transactionId`` / ``valor`` + ``data``.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []

    chaves_prioridade = (
        "transacoes",
        "Transacoes",
        "TRANSACTIONS",
        "movimentos",
        "Movimentos",
        "lancamentos",
        "Lancamentos",
        "listaTransacao",
        "listaMovimento",
        "listaDeTransacoes",
    )
    for k in chaves_prioridade:
        v = payload.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return [x for x in v if isinstance(x, dict)]

    for k in ("transacao", "Transacao", "itemExtrato", "ItemExtrato"):
        v = payload.get(k)
        if isinstance(v, dict) and ("valor" in v or "transactionId" in v):
            return [v]
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return [x for x in v if isinstance(x, dict)]

    d = payload.get("data")
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return [x for x in d if isinstance(x, dict)]
    if isinstance(d, dict):
        inner = extrair_transacoes_payload_sicoob(d)
        if inner:
            return inner

    for v in payload.values():
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
            s0 = v[0]
            if "transactionId" in s0 or (
                "valor" in s0 and ("data" in s0 or "dataLote" in s0 or "dataLancamento" in s0)
            ):
                return [x for x in v if isinstance(x, dict)]

    for v in payload.values():
        if isinstance(v, dict):
            inner = extrair_transacoes_payload_sicoob(v)
            if inner:
                return inner

    return []


def _valor_com_sinal(valor_bruto: Decimal, tipo: str | None) -> Decimal:
    """Define sinal a partir do campo tipo, se o valor vier sempre positivo na API."""
    t = (tipo or "").upper()
    if any(x in t for x in ("DEB", "DÉB", "SAI", "PAG", "RET", "TAR", "TAX")):
        return -abs(valor_bruto)
    if any(x in t for x in ("CRE", "CRÉ", "ENT", "REC", "DEP", "CRED")):
        return abs(valor_bruto)
    return valor_bruto


def _fitid_de_transacao(tx: dict[str, Any]) -> str:
    tid = tx.get("transactionId") or tx.get("id") or tx.get("codigo")
    s = str(tid).strip() if tid is not None else ""
    if not s:
        d = _parse_data(tx.get("data"))
        v = _parse_decimal(tx.get("valor"))
        desc = (tx.get("descricao") or "")[:40]
        s = f"SICOOB|{d}|{v}|{desc}"
    return s[:60]


def importar_extrato_sicoob_json(conta: ContaBancaria, payload: dict[str, Any]) -> tuple[int, int]:
    """
    Lê o objeto JSON retornado pela API (transacoes em lista).
    Retorna (criados, ignorados).
    """
    txs = extrair_transacoes_payload_sicoob(payload)
    if not txs and isinstance(payload, dict):
        logger.warning(
            "Sicoob import: nenhuma lista de transações encontrada. Chaves no JSON: %s",
            list(payload.keys()),
        )

    criados = 0
    ignorados = 0

    # Um ``atomic()`` por linha: em PostgreSQL, ``IntegrityError`` aborta o bloco inteiro;
    # com savepoint (atomic aninhado) as próximas linhas e os ``.exists()`` continuam válidos.
    for tx in txs:
        if not isinstance(tx, dict):
            ignorados += 1
            continue
        d = _parse_data(tx.get("data") or tx.get("dataLancamento") or tx.get("dataLote"))
        if not d:
            ignorados += 1
            continue
        valor_base = _parse_decimal(tx.get("valor"))
        tipo = tx.get("tipo")
        if valor_base >= 0:
            valor = _valor_com_sinal(valor_base, str(tipo) if tipo is not None else None)
        else:
            valor = valor_base

        desc = (tx.get("descricao") or "").strip()
        comp = (tx.get("descInfComplementar") or tx.get("descricaoComplementar") or "").strip()
        historico = desc
        if comp and comp not in desc:
            historico = f"{desc} — {comp}" if desc else comp
        historico = (historico or "Movimento Sicoob")[:255]

        doc = tx.get("numeroDocumento") or tx.get("documento") or ""
        doc = str(doc).strip()[:60] if doc else ""

        cpf = (tx.get("cpfCnpj") or tx.get("cpfCnpjPagador") or "").strip()
        if cpf and cpf not in historico:
            historico = f"{historico} [{cpf}]"[:255]

        fitid = _fitid_de_transacao(tx)
        h = hash_lancamento(conta.id, fitid, d, valor, historico, doc)

        try:
            with transaction.atomic():
                if fitid and Lancamento.objects.filter(conta_id=conta.id, fitid=fitid).exists():
                    ignorados += 1
                    continue
                if Lancamento.objects.filter(conta_id=conta.id, hash_unico=h).exists():
                    ignorados += 1
                    continue
                Lancamento.objects.create(
                    empresa=conta.empresa,
                    conta=conta,
                    banco=conta.banco,
                    fitid=fitid or None,
                    data=d,
                    documento=doc or None,
                    historico=historico,
                    valor=valor,
                    saldo=None,
                    conciliado=False,
                    idconciliacao=None,
                    origem="SICOOB_API",
                    hash_unico=h,
                    extrato_arquivo=None,
                    status_importacao="I",
                )
                criados += 1
        except IntegrityError:
            ignorados += 1
        except Exception as e:
            logger.warning("Sicoob import linha ignorada: %s", e)
            ignorados += 1

    return criados, ignorados


def conta_numero_api_sicoob(conta: ContaBancaria) -> int:
    """Converte campo conta (ex.: 10.091-9) em inteiro para query numeroContaCorrente."""
    raw = (conta.conta or "").strip()
    digitos = "".join(c for c in raw if c.isdigit())
    if not digitos:
        raise ValueError(
            "Conta corrente sem dígitos. Informe o número no cadastro da conta bancária no formato esperado pela API."
        )
    return int(digitos)
