"""Gera um token seguro para MCP_API_TOKEN."""

from __future__ import annotations

import secrets


def main() -> None:
    print(secrets.token_urlsafe(32))


if __name__ == '__main__':
    main()
