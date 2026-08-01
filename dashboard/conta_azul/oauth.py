"""Fluxo OAuth 2.0 Conta Azul (Authorization Code)."""

from __future__ import annotations

import base64
import secrets
from urllib.parse import parse_qs, urlparse

import requests

from dashboard.models import ContaAzulConfig

AUTH_BASE = 'https://auth.contaazul.com'
BOOKMARKLET_CONTA_AZUL = (
    "javascript:(function(){"
    "var q=location.search||'';"
    "if(!q&&location.hash.indexOf('code=')>=0){q='?'+location.hash.replace(/^#/,'');}"
    "var p=new URLSearchParams(q.replace(/^\\?/,''));"
    "var c=p.get('code');"
    "var s=p.get('state')||'';"
    "if(!c){alert('N\\u00e3o achei code nesta URL.\\n\\n'+location.href+'\\n\\nCopie a URL IMEDIATAMENTE ap\\u00f3s autorizar.');return;}"
    "var d=document.createElement('div');"
    "d.innerHTML='<div id=ca-oauth-pop style=\"position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:2147483647;"
    "display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif\">"
    "<div style=\"background:#fff;padding:20px;border-radius:10px;max-width:520px;width:92%;box-shadow:0 8px 32px rgba(0,0,0,.25)\">"
    "<h2 style=\"margin:0 0 8px;font-size:18px;color:#198754\">Code Conta Azul</h2>"
    "<p style=\"margin:0 0 10px;font-size:13px;color:#666\">Copie e cole no assistente DEV</p>"
    "<textarea id=ca-oauth-ta style=\"width:100%;height:72px;font-family:monospace;font-size:12px;"
    "border:1px solid #ccc;border-radius:6px;padding:8px\">'+c+'</textarea>"
    "<p style=\"font-size:11px;color:#888;margin:8px 0 0\">State: '+s+'</p>"
    "<div style=\"margin-top:12px;display:flex;gap:8px\">"
    "<button id=ca-oauth-copy style=\"padding:8px 14px;background:#198754;color:#fff;border:0;"
    "border-radius:6px;cursor:pointer\">Copiar code</button>"
    "<button id=ca-oauth-x style=\"padding:8px 14px;background:#eee;border:0;border-radius:6px;cursor:pointer\">Fechar</button>"
    "</div></div></div>';"
    "document.body.appendChild(d);"
    "document.getElementById('ca-oauth-ta').select();"
    "document.getElementById('ca-oauth-copy').onclick=function(){"
    "var t=document.getElementById('ca-oauth-ta');t.select();"
    "navigator.clipboard.writeText(t.value);this.textContent='Copiado!';};"
    "document.getElementById('ca-oauth-x').onclick=function(){d.remove();};"
    "})();"
)
SCOPE = 'openid profile aws.cognito.signin.user.admin'


class ContaAzulOAuthError(Exception):
    pass


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f'{client_id}:{client_secret}'.encode()
    return base64.b64encode(raw).decode('ascii')


def gerar_state() -> str:
    return secrets.token_urlsafe(32)


def extrair_parametros_oauth(texto: str) -> tuple[str, str]:
    """Extrai code e state de URL completa, query string ou código puro (fluxo DEV)."""
    bruto = (texto or '').strip()
    if not bruto:
        return '', ''
    if bruto.startswith('?'):
        bruto = f'https://local/{bruto}'
    if '://' in bruto or '?' in bruto:
        parsed = urlparse(bruto)
        qs = parse_qs(parsed.query, keep_blank_values=False)
        code = (qs.get('code') or [''])[0].strip()
        state = (qs.get('state') or [''])[0].strip()
        return code, state
    return bruto, ''


def validar_state_oauth(config: ContaAzulConfig, state: str) -> bool:
    esperado = (config.oauth_state or '').strip()
    recebido = (state or '').strip()
    if not esperado:
        return True
    if not recebido:
        return True
    return secrets.compare_digest(esperado, recebido)


def url_autorizacao(
    config: ContaAzulConfig,
    *,
    state: str,
    redirect_uri: str | None = None,
) -> str:
    from urllib.parse import urlencode

    params = {
        'response_type': 'code',
        'client_id': config.client_id.strip(),
        'redirect_uri': (redirect_uri or config.redirect_uri_efetiva()).strip(),
        'state': state,
        'scope': SCOPE,
    }
    return f'{AUTH_BASE}/login?{urlencode(params)}'


def trocar_codigo_por_tokens(
    config: ContaAzulConfig,
    *,
    code: str,
) -> dict:
    from dashboard.conta_azul.config import _descriptografar

    url = f'{AUTH_BASE}/oauth2/token'
    client_secret = _descriptografar(config.client_secret_cifrado)
    headers = {
        'Authorization': f'Basic {_basic_auth(config.client_id.strip(), client_secret)}',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': config.redirect_uri_efetiva(),
    }
    resp = requests.post(url, headers=headers, data=data, timeout=30)
    if resp.status_code != 200:
        raise ContaAzulOAuthError(f'Troca de código falhou ({resp.status_code}): {resp.text[:500]}')
    return resp.json()


def renovar_access_token(config: ContaAzulConfig, refresh_token: str) -> dict:
    from dashboard.conta_azul.config import _descriptografar

    client_secret = _descriptografar(config.client_secret_cifrado)
    url = f'{AUTH_BASE}/oauth2/token'
    headers = {
        'Authorization': f'Basic {_basic_auth(config.client_id.strip(), client_secret)}',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    resp = requests.post(url, headers=headers, data=data, timeout=30)
    if resp.status_code != 200:
        raise ContaAzulOAuthError(f'Renovação falhou ({resp.status_code}): {resp.text[:500]}')
    return resp.json()
