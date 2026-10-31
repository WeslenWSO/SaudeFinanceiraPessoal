"""Respostas legíveis quando o Postgres não conecta ou o schema falta."""

from __future__ import annotations

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse


class DatabaseErrorMiddleware:
    """Evita 500 genérico quando o banco está inacessível ou desatualizado."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except (OperationalError, ProgrammingError) as exc:
            if settings.DEBUG:
                raise
            from SaudeFinanceira.db_schema import capturar_erro_schema

            msg = capturar_erro_schema(exc) or str(exc)
            if 'could not translate host name' in str(exc).lower():
                msg = (
                    'Não foi possível resolver o host do PostgreSQL (DATABASE_URL). '
                    'No Render: SaudeFinanceira → Environment → DATABASE_URL deve ser a '
                    'Internal Database URL do financas-db atual (Add from Database). '
                    'Depois Manual Deploy e abra um Shell novo.'
                )
            elif 'password authentication failed' in str(exc).lower():
                msg = (
                    'Senha do PostgreSQL incorreta em DATABASE_URL. '
                    'Copie de novo a Internal URL em financas-db → Connect.'
                )
            elif not capturar_erro_schema(exc):
                msg = f'Erro de banco de dados: {exc}'

            body = (
                '<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
                '<title>Banco de dados</title></head><body style="font-family:sans-serif;'
                'max-width:42rem;margin:2rem auto;line-height:1.5">'
                '<h1>Banco de dados indisponível</h1>'
                f'<p>{msg}</p>'
                '<p><small>Administrador: Render → Logs ou '
                '<code>python manage.py diagnostico_banco --skip-checks</code> no Shell.</small></p>'
                '</body></html>'
            )
            return HttpResponse(body, status=503, content_type='text/html; charset=utf-8')
