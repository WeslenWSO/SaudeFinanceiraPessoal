"""Normalização de DATABASE_URL (Render / Postgres)."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_PG_HOST_RE = re.compile(r'dpg-[a-z0-9-]+(?:\.[a-z0-9.-]+)?', re.I)


def normalizar_database_url(url: str) -> str:
    """
    Corrige URLs comuns mal coladas:
    - senha + host sem '@' (ex.: ...Senhadpg-xxx-a/db)
    - host interno sem porta (:5432)
    """
    raw = (url or '').strip()
    if not raw or not raw.lower().startswith('postgres'):
        return raw

    if '@' not in raw.split('://', 1)[-1]:
        raw = _inserir_arroba_antes_host_dpg(raw)

    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.scheme:
        return raw

    netloc = parsed.netloc
    if parsed.port is None and '@' in netloc:
        userinfo, _, hostpart = netloc.rpartition('@')
        if hostpart and ':' not in hostpart:
            netloc = f'{userinfo}@{hostpart}:5432'
            parsed = parsed._replace(netloc=netloc)

    return urlunparse(parsed)


def _inserir_arroba_antes_host_dpg(url: str) -> str:
    """postgresql://user:passWORDdpg-host/db → ...passWORD@dpg-host/db"""
    scheme_sep = '://'
    if scheme_sep not in url:
        return url
    scheme, rest = url.split(scheme_sep, 1)
    slash = rest.find('/')
    authority = rest if slash < 0 else rest[:slash]
    path = '' if slash < 0 else rest[slash:]

    match = _PG_HOST_RE.search(authority)
    if not match:
        return url
    host_start = match.start()
    if host_start == 0:
        return url
    before = authority[:host_start]
    host = authority[host_start:]
    if before.endswith('@'):
        return url
    colon = before.find(':')
    if colon < 0:
        return url
    user = before[:colon]
    password = before[colon + 1 :]
    if not user or not password or not host:
        return url
    new_authority = f'{user}:{password}@{host}'
    return f'{scheme}{scheme_sep}{new_authority}{path}'


def host_postgres_da_url(url: str) -> str:
    parsed = urlparse((url or '').strip())
    return (parsed.hostname or '').strip()
