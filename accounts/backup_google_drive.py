"""Envio de arquivos de backup para pasta no Google Drive (compartilhada com a service account)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings


def _folder_id() -> str:
    return (
        os.environ.get('BACKUP_GOOGLE_DRIVE_FOLDER_ID')
        or getattr(settings, 'BACKUP_GOOGLE_DRIVE_FOLDER_ID', '')
        or '1f6ULWD8aAPS5gfG7mGwY2GbG_HrQgz4y'
    ).strip()


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

    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)

    nome = nome_no_drive or path.name
    media = MediaFileUpload(str(path), resumable=True)
    metadata = {'name': nome, 'parents': [folder_id]}
    created = (
        service.files()
        .create(body=metadata, media_body=media, fields='id,name,webViewLink')
        .execute()
    )
    return {
        'file_id': created.get('id'),
        'name': created.get('name'),
        'webViewLink': created.get('webViewLink'),
        'folder_id': folder_id,
    }
