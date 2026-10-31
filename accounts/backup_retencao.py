"""Retenção local: após upload ao Drive, manter N dias e remover do servidor."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.backup_banco import diretorio_backups


def _meta_path(arquivo_local: Path) -> Path:
    return Path(f'{arquivo_local}.drive.json')


def marcar_arquivo_enviado_drive(
    arquivo_local: str | Path,
    *,
    drive_file_id: str,
    drive_name: str = '',
) -> None:
    path = Path(arquivo_local)
    meta = {
        'uploaded_at': timezone.now().isoformat(),
        'drive_file_id': drive_file_id,
        'drive_name': drive_name or path.name,
        'local_name': path.name,
    }
    _meta_path(path).write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')


def dias_retencao_local() -> int:
    return int(getattr(settings, 'BACKUP_LOCAL_RETENTION_DAYS', 5))


def limpar_backups_locais_expirados(*, dias: int | None = None) -> list[str]:
    """
    Remove arquivos locais enviados ao Drive há mais de `dias` dias.
    Só apaga quem tem arquivo .drive.json (upload confirmado).
    """
    dias = dias if dias is not None else dias_retencao_local()
    limite = timezone.now() - timedelta(days=dias)
    removidos: list[str] = []
    pasta = diretorio_backups()

    for meta_file in pasta.glob('*.drive.json'):
        try:
            data = json.loads(meta_file.read_text(encoding='utf-8'))
            uploaded_raw = data.get('uploaded_at') or ''
            uploaded_at = parse_datetime(uploaded_raw)
            if not uploaded_at:
                continue
            if timezone.is_naive(uploaded_at):
                uploaded_at = timezone.make_aware(uploaded_at, timezone.get_current_timezone())
        except (OSError, ValueError, TypeError):
            continue

        if uploaded_at > limite:
            continue

        local_name = data.get('local_name') or meta_file.name.replace('.drive.json', '')
        local_path = pasta / local_name
        if local_path.is_file():
            try:
                local_path.unlink()
                removidos.append(local_name)
            except OSError:
                pass
        try:
            meta_file.unlink()
        except OSError:
            pass

    return removidos
