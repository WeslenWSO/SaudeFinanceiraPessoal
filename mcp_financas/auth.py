"""Verificação do bearer token (MCP_API_TOKEN)."""

from __future__ import annotations

import os
import secrets

from mcp.server.auth.provider import AccessToken


def expected_api_token() -> str:
    return (os.environ.get('MCP_API_TOKEN') or '').strip()


class ApiTokenVerifier:
    """Aceita apenas Authorization: Bearer <MCP_API_TOKEN>."""

    async def verify_token(self, token: str) -> AccessToken | None:
        expected = expected_api_token()
        if not expected or not token:
            return None
        if not secrets.compare_digest(token.strip(), expected):
            return None
        return AccessToken(
            token=token,
            client_id='mcp-financas',
            scopes=['tools'],
            subject='mcp-api',
        )
