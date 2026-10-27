"""Mensagens quando o PostgreSQL/SQLite não reflete o código (migrate pendente)."""

from __future__ import annotations

from django.db.utils import OperationalError, ProgrammingError


def erro_parece_schema_desatualizado(exc: BaseException) -> bool:
    msg = str(exc).lower()
    needles = (
        'does not exist',
        'no such column',
        'no such table',
        'column',
        'undefinedcolumn',
        'programmingerror',
        'relation',
    )
    return any(n in msg for n in needles)


def mensagem_schema_desatualizado(contexto: str = '') -> str:
    base = (
        'O banco de dados no servidor está desatualizado em relação ao código '
        '(migration pendente ou deploy incompleto). '
        'No Render Shell, execute: python manage.py migrate --noinput '
        'e reinicie o serviço. '
    )
    if contexto:
        return base + f'({contexto})'
    return base.strip()


def capturar_erro_schema(exc: BaseException, *, contexto: str = '') -> str | None:
    if isinstance(exc, (ProgrammingError, OperationalError)):
        return mensagem_schema_desatualizado(contexto)
    return None
