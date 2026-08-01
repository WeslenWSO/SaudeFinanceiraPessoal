"""Cliente HTTP API Conta Azul v1."""

from __future__ import annotations

from typing import Any

import requests

from dashboard.conta_azul.config import ContaAzulCredentials, credenciais_da_empresa, gravar_tokens
from dashboard.models import ContaAzulConfig

API_BASE = 'https://api-v2.contaazul.com'


class ContaAzulAPIError(Exception):
    pass


class ContaAzulClient:
    def __init__(self, creds: ContaAzulCredentials):
        self.creds = creds

    @classmethod
    def para_empresa(cls, empresa) -> ContaAzulClient:
        creds = credenciais_da_empresa(empresa)
        if not creds:
            raise ContaAzulAPIError('Conta Azul não configurada para esta empresa.')
        return cls(creds)

    def _config(self) -> ContaAzulConfig | None:
        if not self.creds.config_id:
            return None
        return ContaAzulConfig.objects.filter(pk=self.creds.config_id).first()

    def _garantir_token(self, *, forcar_renovacao: bool = False) -> str:
        from django.utils import timezone

        from dashboard.conta_azul.oauth import renovar_access_token

        token = self.creds.access_token
        expira = self.creds.token_expira_em
        if not forcar_renovacao and token and expira and expira > timezone.now():
            return token
        if not self.creds.refresh_token:
            raise ContaAzulAPIError(
                'Conta Azul não conectada ou sessão expirada. '
                'Abra Configuração Conta Azul e clique em Conectar/Reconectar '
                '(ou cole o código manual em ambiente DEV).'
            )
        cfg = self._config()
        if not cfg:
            raise ContaAzulAPIError('Configuração não encontrada para renovar token.')
        try:
            payload = renovar_access_token(cfg, self.creds.refresh_token)
        except ContaAzulOAuthError as exc:
            raise ContaAzulAPIError(
                f'Não foi possível renovar o token ({exc}). Clique em Reconectar na configuração.'
            ) from exc
        gravar_tokens(
            cfg,
            access_token=payload.get('access_token', ''),
            refresh_token=payload.get('refresh_token', self.creds.refresh_token),
            expires_in=int(payload.get('expires_in', 3600)),
        )
        self.creds = credenciais_da_empresa(cfg.empresa)
        if not self.creds or not self.creds.access_token:
            raise ContaAzulAPIError('Falha ao renovar token.')
        return self.creds.access_token

    def _request(self, method: str, path: str, **kwargs) -> Any:
        token = self._garantir_token()
        url = f'{API_BASE}{path}'
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {token}'
        resp = requests.request(method, url, headers=headers, timeout=kwargs.pop('timeout', 45), **kwargs)
        if resp.status_code == 401:
            token = self._garantir_token(forcar_renovacao=True)
            headers['Authorization'] = f'Bearer {token}'
            resp = requests.request(method, url, headers=headers, timeout=45, **kwargs)
        if resp.status_code >= 400:
            msg = resp.text[:500]
            if resp.status_code == 401 and 'ERP' in msg:
                raise ContaAzulAPIError(
                    'Conta Azul recusou o token (401): na autorização OAuth use o e-mail e senha '
                    'do ERP da empresa (ex.: Medicinarte em app.contaazul.com), não o login do '
                    'portal de desenvolvedor (DEV-Wes). Desconecte, reconecte escolhendo a empresa '
                    'correta e tente sincronizar de novo.'
                )
            raise ContaAzulAPIError(f'{method} {path} → {resp.status_code}: {msg}')
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request('GET', path, params=params or {})

    def paginar_todos(self, path: str, params: dict | None = None, *, chave_itens: str = 'itens') -> list:
        params = dict(params or {})
        params.setdefault('pagina', 1)
        params.setdefault('tamanho_pagina', 100)
        todos: list = []
        while True:
            data = self.get(path, params)
            itens = data.get(chave_itens) or data.get('data') or []
            if isinstance(itens, list):
                todos.extend(itens)
            total = data.get('itens_totais') or data.get('total') or len(todos)
            if len(todos) >= int(total) or not itens:
                break
            params['pagina'] = int(params.get('pagina', 1)) + 1
        return todos

    def buscar_categorias(self, **filtros) -> list:
        filtros.setdefault('apenas_filhos', False)
        return self.paginar_todos('/v1/categorias', filtros)

    def buscar_categorias_dre(self) -> dict:
        return self.get('/v1/financeiro/categorias-dre')

    def buscar_centros_custo(self, **filtros) -> list:
        return self.paginar_todos('/v1/centro-de-custo', filtros)

    def buscar_contas_financeiras(self, **filtros) -> list:
        filtros.setdefault('apenas_ativo', True)
        return self.paginar_todos('/v1/conta-financeira', filtros)

    def buscar_saldo_atual_conta(self, conta_id: str) -> dict:
        cid = (conta_id or '').strip()
        if not cid:
            return {}
        return self.get(f'/v1/conta-financeira/{cid}/saldo-atual')

    def buscar_receitas(self, **filtros) -> list:
        return self.paginar_todos(
            '/v1/financeiro/eventos-financeiros/contas-a-receber/buscar',
            filtros,
        )

    def buscar_despesas(self, **filtros) -> list:
        return self.paginar_todos(
            '/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar',
            filtros,
        )

    def buscar_transferencias(self, **filtros) -> list:
        return self.paginar_todos(
            '/v1/financeiro/transferencias/buscar',
            filtros,
        )

    def buscar_pessoas(self, tipo_perfil: str, **filtros) -> list:
        filtros = dict(filtros)
        filtros['tipo_perfil'] = tipo_perfil
        filtros.setdefault('com_endereco', True)
        return self.paginar_todos('/v1/pessoas', filtros)

    def buscar_clientes(self, **filtros) -> list:
        return self.buscar_pessoas('Cliente', **filtros)

    def buscar_fornecedores(self, **filtros) -> list:
        return self.buscar_pessoas('Fornecedor', **filtros)

    def testar_conexao(self) -> dict:
        return self.get('/v1/categorias', {'pagina': 1, 'tamanho_pagina': 1})
