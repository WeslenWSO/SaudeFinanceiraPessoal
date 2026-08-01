#!/usr/bin/env python
"""
Corrige sequências PostgreSQL (serial/identity) após importação SQLite com PKs explícitos.

  python scripts/corrigir_sequencias_postgres.py
  python scripts/corrigir_sequencias_postgres.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
if not os.environ.get("DATABASE_URL"):
    url_file = ROOT / "render_db.url"
    if url_file.is_file():
        os.environ["DATABASE_URL"] = url_file.read_text(encoding="utf-8").strip()

import django

django.setup()

from django.apps import apps
from django.db import connection


def _tabelas_com_serial():
    """Tabelas de modelos Django com pk auto-increment."""
    for model in apps.get_models():
        pk = model._meta.pk
        if pk.get_internal_type() not in ("AutoField", "BigAutoField"):
            continue
        yield model._meta.db_table, pk.column


def corrigir(dry_run: bool = False) -> int:
    if connection.vendor != "postgresql":
        print("Este script só se aplica a PostgreSQL.", file=sys.stderr)
        return 1

    corrigidas = 0
    with connection.cursor() as cursor:
        for tabela, coluna in sorted(set(_tabelas_com_serial())):
            try:
                cursor.execute(
                    "SELECT to_regclass(%s)",
                    [tabela],
                )
                if cursor.fetchone()[0] is None:
                    continue
                cursor.execute(
                    "SELECT pg_get_serial_sequence(%s, %s)",
                    [tabela, coluna],
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    continue
                seq = row[0]
                cursor.execute(f'SELECT COALESCE(MAX("{coluna}"), 0) FROM "{tabela}"')
                max_id = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT last_value FROM {seq}")
                last_val = cursor.fetchone()[0]
                if max_id > last_val:
                    print(f"  {tabela}: max_id={max_id} seq_last={last_val} -> setval({max_id})")
                    if not dry_run:
                        cursor.execute("SELECT setval(%s, %s, true)", [seq, max_id])
                    corrigidas += 1
            except Exception as exc:
                print(f"  {tabela}: ignorado ({exc})")

    if dry_run:
        print(f"\n(dry-run) {corrigidas} sequência(s) precisam de ajuste.")
    else:
        print(f"\n{corrigidas} sequência(s) corrigida(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print("=== Corrigir sequências PostgreSQL ===")
    return corrigir(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
