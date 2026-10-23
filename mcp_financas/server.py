"""Servidor MCP (FastMCP) — tools do app Saúde Financeira."""

from __future__ import annotations

import os

from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import FastMCP

from mcp_financas.auth import ApiTokenVerifier, expected_api_token
from mcp_financas.tools_impl import (
    health_check,
    listar_empresas,
    resumo_faturamento,
    resumo_fluxo_caixa,
)


def create_mcp() -> FastMCP:
    host = os.environ.get('MCP_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT') or os.environ.get('MCP_PORT', '8000'))
    token_verifier: ApiTokenVerifier | None = None
    if expected_api_token():
        token_verifier = ApiTokenVerifier()

    mcp = FastMCP(
        'saude-financeira',
        instructions=(
            'Consultas read-only ao sistema Saúde Financeira (empresas, faturamento médico, '
            'fluxo de caixa). Informe empresa_id quando aplicável.'
        ),
        host=host,
        port=port,
        token_verifier=token_verifier,
        stateless_http=os.environ.get('MCP_STATELESS_HTTP', 'true').lower()
        in ('1', 'true', 'yes'),
    )

    @mcp.tool()
    def mcp_health_check() -> str:
        """Verifica conexão com o banco."""
        return health_check()

    @mcp.tool()
    def mcp_listar_empresas(apenas_ativas: bool = True) -> str:
        """Lista empresas cadastradas (id, razão, CNPJ)."""
        return listar_empresas(apenas_ativas=apenas_ativas)

    @mcp.tool()
    def mcp_resumo_faturamento(
        empresa_id: int,
        data_inicio: str,
        data_fim: str,
    ) -> str:
        """Resumo de faturamento médico no período (AAAA-MM-DD)."""
        return resumo_faturamento(empresa_id, data_inicio, data_fim)

    @mcp.tool()
    def mcp_resumo_fluxo_caixa(empresa_id: int, ano: int) -> str:
        """Totais mensais de receitas/despesas/resultado (modo planilha)."""
        return resumo_fluxo_caixa(empresa_id, ano)

    return mcp


def run(transport: str = 'stdio') -> None:
    if transport != 'stdio' and not expected_api_token():
        raise SystemExit(
            'Defina MCP_API_TOKEN no ambiente para transporte HTTP/SSE (Render ou remoto).'
        )
    mcp = create_mcp()
    mcp.run(transport=transport)
