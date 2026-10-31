"""Envio de arquivos de backup para pasta no Google Drive (compartilhada com a service account)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings


def _folder_id() -> str:
    env = (
        os.environ.get('BACKUP_GOOGLE_DRIVE_FOLDER_ID')
        or getattr(settings, 'BACKUP_GOOGLE_DRIVE_FOLDER_ID', '')
        or ''
    ).strip()
    if env:
        return env
    try:
        from accounts.backup_config import drive_folder_id_configurado

        db_id = drive_folder_id_configurado()
        if db_id:
            return db_id
    except Exception:
        pass
    return '1f6ULWD8aAPS5gfG7mGwY2GbG_HrQgz4y'


def _credenciais_service_account() -> dict | None:
    raw_json = (os.environ.get('BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON') or '').strip()
    if raw_json:
        return json.loads(raw_json)
    path = (
        os.environ.get('BACKUP_GOOGLE_SERVICE_ACCOUNT_FILE')
        or getattr(settings, 'BACKUP_GOOGLE_SERVICE_ACCOUNT_FILE', '')
        or ''
    ).strip()
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text(encoding='utf-8'))
    return None


def drive_configurado() -> bool:
    return bool(_folder_id() and _credenciais_service_account())


def email_service_account_drive() -> str:
    info = _credenciais_service_account()
    if not info:
        return ''
    return str(info.get('client_email') or '').strip()


def enviar_backup_info_para_drive(info: dict) -> list[dict]:
    """Envia arquivo principal + extras (sql.gz + json) e aplica retenção local."""
    from accounts.backup_retencao import limpar_backups_locais_expirados, marcar_arquivo_enviado_drive

    if not drive_configurado():
        raise RuntimeError(
            'Google Drive não configurado: defina BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON no Render '
            'e compartilhe a pasta BKP_SAUDE com a service account (Editor).'
        )

    uploads: list[dict] = []
    caminhos: list[Path] = []
    principal = (info.get('caminho') or '').strip()
    if principal:
        caminhos.append(Path(principal))
    for extra in info.get('extras') or []:
        p = (extra.get('caminho') or '').strip()
        if p:
            caminhos.append(Path(p))

    if not caminhos:
        raise RuntimeError('Nenhum arquivo de backup para enviar.')

    erros: list[str] = []
    for path in caminhos:
        try:
            up = enviar_arquivo_para_drive(path)
            marcar_arquivo_enviado_drive(path, drive_file_id=up.get('file_id') or '', drive_name=up.get('name') or '')
            uploads.append(up)
        except Exception as exc:
            erros.append(f'{path.name}: {exc}')

    limpar_backups_locais_expirados()

    if erros and not uploads:
        raise RuntimeError('Falha ao enviar ao Drive — ' + '; '.join(erros))
    if erros:
        raise RuntimeError(
            'Enviado parcialmente ao Drive. OK: '
            + ', '.join(u.get('name', '') for u in uploads)
            + '. Falhas: '
            + '; '.join(erros)
        )
    return uploads


def enviar_arquivo_para_drive(caminho_local: str | Path, *, nome_no_drive: str | None = None) -> dict:
    """
    Faz upload para a pasta BKP_SAUDE (ou BACKUP_GOOGLE_DRIVE_FOLDER_ID).
    A pasta no Drive de weslensioliveira@gmail.com deve estar compartilhada com o e-mail
    da service account (Editor).
    """
    path = Path(caminho_local)
    if not path.is_file():
        raise FileNotFoundError(f'Arquivo não encontrado: {path}')

    creds_info = _credenciais_service_account()
    if not creds_info:
        raise RuntimeError(
            'Defina BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON (JSON inline) ou '
            'BACKUP_GOOGLE_SERVICE_ACCOUNT_FILE no Render.'
        )

    folder_id = _folder_id()
    if not folder_id:
        raise RuntimeError('BACKUP_GOOGLE_DRIVE_FOLDER_ID não configurado.')

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    scopes = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)

    nome = nome_no_drive or path.name
    media = MediaFileUpload(str(path), resumable=True)
    metadata = {'name': nome, 'parents': [folder_id]}
    try:
        created = (
            service.files()
            .create(
                body=metadata,
                media_body=media,
                fields='id,name,webViewLink',
                supportsAllDrives=True,
            )
            .execute()
        )
    except Exception as exc:
        email = str(creds_info.get('client_email') or '')
        raise RuntimeError(
            f'Google Drive recusou o upload ({exc}). '
            f'Confira: API Drive ativa, pasta compartilhada com {email or "service account"} '
            f'(Editor), folder id={folder_id}.'
        ) from exc
    return {
        'file_id': created.get('id'),
        'name': created.get('name'),
        'webViewLink': created.get('webViewLink'),
        'folder_id': folder_id,
    }
