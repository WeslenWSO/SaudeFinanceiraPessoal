"""Geração de backup completo do banco (JSON dumpdata e/ou pg_dump)."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from datetime import datetime
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command


def diretorio_backups() -> Path:
    base = getattr(settings, 'BACKUP_DATABASE_DIR', None)
    if base:
        path = Path(base)
    else:
        path = Path(settings.BASE_DIR) / 'backups'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _engine_postgres() -> bool:
    engine = settings.DATABASES['default'].get('ENGINE', '')
    return 'postgresql' in engine


def gerar_backup_json() -> str:
    buffer = StringIO()
    call_command(
        'dumpdata',
        '--natural-foreign',
        '--natural-primary',
        '--indent', '2',
        exclude=['contenttypes', 'auth.Permission'],
        stdout=buffer,
    )
    return buffer.getvalue()


def _pg_dump_disponivel() -> str | None:
    return shutil.which('pg_dump')


def gerar_backup_sql_postgres() -> bytes:
    if not _engine_postgres():
        raise RuntimeError('Backup SQL disponível apenas para PostgreSQL.')

    pg_dump = _pg_dump_disponivel()
    if not pg_dump:
        raise RuntimeError('pg_dump não encontrado no PATH.')

    db = settings.DATABASES['default']
    env = os.environ.copy()
    password = db.get('PASSWORD') or ''
    if password:
        env['PGPASSWORD'] = str(password)

    cmd = [
        pg_dump,
        '-h', str(db.get('HOST') or 'localhost'),
        '-p', str(db.get('PORT') or '5432'),
        '-U', str(db.get('USER') or 'postgres'),
        '-d', str(db.get('NAME') or ''),
        '--no-owner',
        '--no-acl',
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        env=env,
        check=False,
        timeout=getattr(settings, 'BACKUP_DATABASE_TIMEOUT', 600),
    )
    if result.returncode != 0:
        stderr = (result.stderr or b'').decode('utf-8', errors='replace').strip()
        raise RuntimeError(stderr or f'pg_dump falhou (código {result.returncode}).')

    return result.stdout


def criar_backup_completo() -> dict:
    """
    Gera backup, grava em BACKUP_DATABASE_DIR e retorna metadados do arquivo principal.
    """
    pasta = diretorio_backups()
    ts = _timestamp()
    info: dict = {
        'arquivo': '',
        'caminho': '',
        'formato': '',
        'tamanho': 0,
        'extras': [],
    }

    if _engine_postgres() and _pg_dump_disponivel():
        sql_bytes = gerar_backup_sql_postgres()
        nome = f'backup_{ts}.sql.gz'
        caminho = pasta / nome
        with gzip.open(caminho, 'wb') as fh:
            fh.write(sql_bytes)
        info.update({
            'arquivo': nome,
            'caminho': str(caminho),
            'formato': 'sql.gz',
            'tamanho': caminho.stat().st_size,
        })
    else:
        json_text = gerar_backup_json()
        nome = f'backup_{ts}.json'
        caminho = pasta / nome
        caminho.write_text(json_text, encoding='utf-8')
        info.update({
            'arquivo': nome,
            'caminho': str(caminho),
            'formato': 'json',
            'tamanho': caminho.stat().st_size,
        })

    # Cópia JSON complementar quando o principal for SQL (restauração via loaddata)
    if info['formato'] == 'sql.gz':
        try:
            json_text = gerar_backup_json()
            nome_json = f'backup_{ts}.json'
            caminho_json = pasta / nome_json
            caminho_json.write_text(json_text, encoding='utf-8')
            info['extras'].append({
                'arquivo': nome_json,
                'caminho': str(caminho_json),
                'formato': 'json',
                'tamanho': caminho_json.stat().st_size,
            })
        except Exception:
            pass

    return info


def listar_backups_locais(limite: int = 30) -> list[dict]:
    pasta = diretorio_backups()
    arquivos = []
    for path in pasta.iterdir():
        if not path.is_file():
            continue
        if not (path.name.endswith('.json') or path.name.endswith('.sql.gz') or path.suffix == '.sql'):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        arquivos.append({
            'nome': path.name,
            'caminho': str(path),
            'tamanho': stat.st_size,
            'modificado': datetime.fromtimestamp(stat.st_mtime),
        })
    arquivos.sort(key=lambda x: x['modificado'], reverse=True)
    return arquivos[:limite]


def caminho_backup_seguro(nome: str) -> Path | None:
    """Resolve arquivo apenas dentro do diretório de backups (anti path traversal)."""
    if not nome or '..' in nome or '/' in nome or '\\' in nome:
        return None
    pasta = diretorio_backups().resolve()
    path = (pasta / nome).resolve()
    if path.parent != pasta or not path.is_file():
        return None
    return path
