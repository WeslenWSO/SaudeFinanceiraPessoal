#!/usr/bin/env python
"""Lista diferenças de contagem entre SQLite e Postgres."""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE = ROOT / "db.sqlite3"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")


def sqlite_counts() -> Counter:
    c: Counter = Counter()
    conn = sqlite3.connect(SQLITE)
    try:
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                if n:
                    c[table] = n
            except sqlite3.Error:
                pass
    finally:
        conn.close()
    return c


def postgres_counts() -> Counter:
    if not os.environ.get("DATABASE_URL"):
        url = ROOT / "render_db.url"
        if url.is_file():
            os.environ["DATABASE_URL"] = url.read_text(encoding="utf-8").strip()
    import django

    django.setup()
    from django.apps import apps

    c: Counter = Counter()
    for model in apps.get_models():
        if model._meta.app_label in {"contenttypes", "admin"}:
            continue
        try:
            n = model.objects.count()
            if n:
                c[model._meta.db_table] = n
        except Exception:
            pass
    return c


def main() -> int:
    sq, pg = sqlite_counts(), postgres_counts()
    diffs = []
    for t in sorted(set(sq) | set(pg), key=str.lower):
        s, p = sq.get(t, 0), pg.get(t, 0)
        if s != p:
            diffs.append((t, s, p, p - s))
    print(f"Diferenças: {len(diffs)}\n")
    for t, s, p, d in sorted(diffs, key=lambda x: abs(x[3]), reverse=True):
        print(f"  {t}: sqlite={s} postgres={p} diff={d:+d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
