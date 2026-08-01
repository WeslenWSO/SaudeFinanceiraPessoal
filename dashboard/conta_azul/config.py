"""Resolve credenciais Conta Azul por empresa ou variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from dashboard.models import ContaAzulConfig
from empresa.nfse_nacional_crypto import criptografar_senha_pfx, descriptografar_senha_pfx


@dataclass(frozen=True)
class ContaAzulCredentials:
    client_id: str
    client_secret: str
    redirect_uri: str
    access_token: str
    refresh_token: str
    token_expira_em: datetime | None
    config_id: int
    empresa_id: int


def gravar_client_secret(config: ContaAzulConfig, secret: str) -> None:
    s = (secret or '').strip()
    if s:
        config.client_secret_cifrado = criptografar_senha_pfx(s)


def gravar_tokens(
    config: ContaAzulConfig,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    config.access_token_cifrado = criptografar_senha_pfx(access_token or '')
    if refresh_token:
        config.refresh_token_cifrado = criptografar_senha_pfx(refresh_token)
    config.token_expira_em = timezone.now() + timedelta(seconds=max(0, int(expires_in) - 60))
    config.conectado_em = timezone.now()
    config.oauth_state = ''
    config.save(
        update_fields=[
            'access_token_cifrado',
            'refresh_token_cifrado',
            'token_expira_em',
            'conectado_em',
            'oauth_state',
            'atualizado_em',
        ]
    )


def limpar_tokens(config: ContaAzulConfig) -> None:
    config.access_token_cifrado = ''
    config.refresh_token_cifrado = ''
    config.token_expira_em = None
    config.conectado_em = None
    config.oauth_state = ''
    config.save(
        update_fields=[
            'access_token_cifrado',
            'refresh_token_cifrado',
            'token_expira_em',
            'conectado_em',
            'oauth_state',
            'atualizado_em',
        ]
    )


def _descriptografar(valor_cifrado: str) -> str:
    if not valor_cifrado:
        return ''
    return descriptografar_senha_pfx(valor_cifrado) or ''


def credenciais_da_empresa(empresa) -> ContaAzulCredentials | None:
    cfg = getattr(empresa, 'conta_azul_config', None)
    if cfg and cfg.ativo and cfg.credenciais_preenchidas():
        return ContaAzulCredentials(
            client_id=cfg.client_id.strip(),
            client_secret=_descriptografar(cfg.client_secret_cifrado),
            redirect_uri=cfg.redirect_uri_efetiva(),
            access_token=_descriptografar(cfg.access_token_cifrado),
            refresh_token=_descriptografar(cfg.refresh_token_cifrado),
            token_expira_em=cfg.token_expira_em,
            config_id=cfg.pk,
            empresa_id=empresa.pk,
        )

    client_id = (os.environ.get('CONTA_AZUL_CLIENT_ID') or '').strip()
    client_secret = (os.environ.get('CONTA_AZUL_CLIENT_SECRET') or '').strip()
    redirect_uri = (
        os.environ.get('CONTA_AZUL_REDIRECT_URI') or ContaAzulConfig.REDIRECT_PROD
    ).strip()
    if client_id and client_secret:
        return ContaAzulCredentials(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            access_token='',
            refresh_token='',
            token_expira_em=None,
            config_id=0,
            empresa_id=getattr(empresa, 'pk', 0) or 0,
        )
    return None


def config_da_empresa(empresa) -> ContaAzulConfig | None:
    try:
        return empresa.conta_azul_config
    except ContaAzulConfig.DoesNotExist:
        return None


def obter_ou_criar_config(empresa) -> ContaAzulConfig:
    cfg, _ = ContaAzulConfig.objects.get_or_create(empresa=empresa)
    return cfg
