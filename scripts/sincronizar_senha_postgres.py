#!/usr/bin/env python
"""
Copia o hash de senha do SQLite local (db.sqlite3) para o PostgreSQL no Render.

Use quando o usuario existe no Postgres mas o login falha (senha alterada localmente
depois do backup, ou hash divergente apos import).

  set DATABASE_URL=postgresql://...   (External URL do financas-db)
  python scripts/sincronizar_senha_postgres.py saude
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE = ROOT / 'db.sqlite3'
sys.path.insert(0, str(ROOT))


def _hash_sqlite(username: str) -> tuple[str, bool] | None:
    if not SQLITE.is_file():
        print(f'SQLite nao encontrado: {SQLITE}', file=sys.stderr)
        return None
    conn = sqlite3.connect(SQLITE)
    try:
        row = conn.execute(
            'SELECT password, is_active FROM auth_user WHERE username = ? COLLATE NOCASE',
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        print(f'Usuario "{username}" nao existe no SQLite local.', file=sys.stderr)
        return None
    return row[0], bool(row[1])


def main() -> int:
    if len(sys.argv) < 2:
        print('Uso: python scripts/sincronizar_senha_postgres.py USUARIO|--todos', file=sys.stderr)
        return 1

    target = sys.argv[1].strip()
    if not target:
        print('Informe o username ou --todos.', file=sys.stderr)
        return 1

    url_file = ROOT / 'render_db.url'
    if not os.environ.get('DATABASE_URL') and url_file.is_file():
        os.environ['DATABASE_URL'] = url_file.read_text(encoding='utf-8').strip()

    if not os.environ.get('DATABASE_URL'):
        print('Defina DATABASE_URL (External URL do financas-db no Render).', file=sys.stderr)
        return 1

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
    os.chdir(ROOT)
    import django

    django.setup()
    from django.contrib.auth.models import User

    if target == '--todos':
        conn = sqlite3.connect(SQLITE)
        try:
            usernames = [r[0] for r in conn.execute('SELECT username FROM auth_user ORDER BY username')]
        finally:
            conn.close()
    else:
        usernames = [target]

    ok = 0
    for username in usernames:
        local = _hash_sqlite(username)
        if not local:
            continue
        password_hash, is_active = local
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            print(f'PULADO: {username} nao existe no PostgreSQL.')
            continue
        user.password = password_hash
        user.is_active = is_active
        user.is_staff = True
        user.save(update_fields=['password', 'is_active', 'is_staff'])
        print(f'OK: {user.username}')
        ok += 1

    print(f'Sincronizados: {ok}/{len(usernames)}')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
