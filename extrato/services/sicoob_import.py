"""Importa lançamentos do extrato retornado pela API Sicoob para o modelo Lancamento."""
from __future__ import annotations

import logging
from typing import Any

from SaudeFinanceira.openfinanceSicoob import executar_de_empresa_conta

from ..models import ContaBancaria
from .sicoob_importer import extrair_transacoes_payload_sicoob, importar_extrato_sicoob_json

logger = logging.getLogger(__name__)


def importar_extrato_sicoob_para_conta(
    conta: ContaBancaria,
    mes: int,
    ano: int,
    *,
    dia_inicial: int | None = None,
    dia_final: int | None = None,
) -> tuple[int, int, str]:
    """
    Consulta a API e grava Lancamento (origem SICOOB_API).
    Retorna (criados, ignorados, mensagem_resumo).
    """
    raw = (getattr(conta, "sicoob_numero_conta_corrente_api", None) or "").strip()
    if not raw:
        raise ValueError(
            "Informe o número da conta corrente para a API Sicoob no cadastro da conta bancária "
            "(campo usado em numeroContaCorrente no portal do desenvolvedor)."
        )
    if not "".join(ch for ch in raw if ch.isdigit()):
        raise ValueError("Número da conta corrente API inválido (informe os dígitos do número da conta).")

    empresa = conta.empresa
    logger.info(
        "Sicoob import (web) | empresa_id=%s conta_id=%s mes=%s ano=%s dia_inicial=%s dia_final=%s | conta_cc_campo=%s",
        empresa.pk,
        conta.pk,
        mes,
        ano,
        dia_inicial,
        dia_final,
        raw,
    )
    payload = executar_de_empresa_conta(
        empresa.pk,
        conta.pk,
        mes,
        ano,
        dia_inicial=dia_inicial,
        dia_final=dia_final,
    )
    if payload is None:
        raise ValueError(
            "Não foi possível obter o extrato na API Sicoob (token OAuth ou GET extrato falhou). "
            "Verifique Client ID, certificado (.pfx) e senha na empresa, número da conta API na conta bancária "
            "e se o app está liberado para client_credentials + mTLS."
        )
    if isinstance(payload, list):
        payload = {"transacoes": [x for x in payload if isinstance(x, dict)]}
    elif not isinstance(payload, dict):
        payload = {}

    txs = extrair_transacoes_payload_sicoob(payload)
    raiz = list(payload.keys()) if isinstance(payload, dict) else []
    logger.info(
        "Sicoob import | transações reconhecidas no JSON: %s | chaves_raiz=%s",
        len(txs),
        raiz[:30],
    )

    criados, ignorados = importar_extrato_sicoob_json(conta, payload)

    msg = f"API Sicoob: {criados} lançamento(s) importado(s), {ignorados} ignorado(s)/duplicado(s)."
    return criados, ignorados, msg
