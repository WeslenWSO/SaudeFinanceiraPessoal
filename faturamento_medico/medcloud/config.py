"""Resolve credenciais MedCloud da empresa ou variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass

from empresa.nfse_nacional_crypto import criptografar_senha_pfx, descriptografar_senha_pfx


@dataclass(frozen=True)
class MedcloudCredentials:
    ris_base_url: str
    ris_username: str
    ris_password: str
    ris_clinic_id: int
    ris_lista_agendas_path: str
    his_base_url: str
    his_api_key: str


def _env_int(name: str, default: int = 0) -> int:
    raw = (os.environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def credenciais_da_empresa(empresa) -> MedcloudCredentials | None:
    """Retorna credenciais da MedcloudConfig ou fallback em env vars."""
    cfg = getattr(empresa, 'medcloud_config', None)
    if cfg and cfg.ativo:
        senha = descriptografar_senha_pfx(cfg.ris_password_cifrada or '') if cfg.ris_password_cifrada else ''
        api_key = descriptografar_senha_pfx(cfg.his_api_key_cifrada or '') if cfg.his_api_key_cifrada else ''
        if cfg.ris_username and senha and cfg.ris_clinic_id:
            return MedcloudCredentials(
                ris_base_url=(cfg.ris_base_url or 'https://api.ris.medcloud.co').rstrip('/'),
                ris_username=cfg.ris_username,
                ris_password=senha,
                ris_clinic_id=int(cfg.ris_clinic_id),
                ris_lista_agendas_path=cfg.ris_lista_agendas_path or '/schedules',
                his_base_url=(cfg.his_base_url or 'https://his.medcloud.co/v1/his').rstrip('/'),
                his_api_key=api_key,
            )

    username = (os.environ.get('MEDCLOUD_RIS_USERNAME') or '').strip()
    password = (os.environ.get('MEDCLOUD_RIS_PASSWORD') or '').strip()
    clinic_id = _env_int('MEDCLOUD_RIS_CLINIC_ID')
    if username and password and clinic_id:
        return MedcloudCredentials(
            ris_base_url=(os.environ.get('MEDCLOUD_RIS_BASE_URL') or 'https://api.ris.medcloud.co').rstrip('/'),
            ris_username=username,
            ris_password=password,
            ris_clinic_id=clinic_id,
            ris_lista_agendas_path=os.environ.get('MEDCLOUD_RIS_SCHEDULES_PATH', '/schedules'),
            his_base_url=(os.environ.get('MEDCLOUD_HIS_BASE_URL') or 'https://his.medcloud.co/v1/his').rstrip('/'),
            his_api_key=(os.environ.get('MEDCLOUD_HIS_API_KEY') or '').strip(),
        )
    return None


def gravar_senha_ris(config, senha_plana: str) -> None:
    senha = (senha_plana or '').strip()
    if senha:
        config.ris_password_cifrada = criptografar_senha_pfx(senha)


def gravar_api_key_his(config, api_key: str) -> None:
    chave = (api_key or '').strip()
    if chave:
        config.his_api_key_cifrada = criptografar_senha_pfx(chave)
