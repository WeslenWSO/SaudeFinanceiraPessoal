#!/usr/bin/env python
"""
Compara contagens backup_render.json x PostgreSQL (DATABASE_URL) x SQLite local.

  set DATABASE_URL=postgresql://...
  python scripts/diagnostico_importacao.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "backup_render.json"
SQLITE = ROOT / "db.sqlite3"

sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")


def _backup_counts() -> Counter:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return Counter(r["model"] for r in rows)


def _sqlite_counts() -> Counter:
    if not SQLITE.is_file():
        return Counter()
    conn = sqlite3.connect(SQLITE)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        c = Counter()
        for table in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            except sqlite3.Error:
                continue
            if n:
                app_model = table.replace("_", ".", 1) if "_" in table else table
                # django table auth_user -> auth.user
                parts = table.split("_", 1)
                if len(parts) == 2:
                    app_model = f"{parts[0]}.{parts[1]}"
                c[app_model] = n
        return c
    finally:
        conn.close()


def _postgres_counts() -> Counter:
    import django

    django.setup()
    from django.apps import apps

    c = Counter()
    for model in apps.get_models():
        if model._meta.app_label in {"contenttypes", "admin"}:
            continue
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        try:
            n = model.objects.count()
        except Exception:
            continue
        if n:
            c[label] = n
    return c


def _norm_key(model_label: str) -> str:
    return model_label.lower().replace("_", "")


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 1
    if not FIXTURE.is_file():
        print(f"Arquivo nao encontrado: {FIXTURE}", file=sys.stderr)
        return 1

    backup = _backup_counts()
    pg = _postgres_counts()

    # Map backup labels to postgres (same format app.model)
    all_models = sorted(set(backup) | set(pg), key=lambda x: x.lower())

    ok = []
    parcial = []
    faltando = []
    so_pg = []
    vazio_backup = []

    print("=== Diagnostico importacao (backup vs PostgreSQL) ===\n")
    print(f"{'Modelo':<55} {'Backup':>8} {'Postgres':>8}  Status")
    print("-" * 85)

    for model in all_models:
        b = backup.get(model, 0)
        p = pg.get(model, 0)
        if b == 0 and p == 0:
            continue
        if b == 0 and p > 0:
            so_pg.append((model, b, p))
            status = "EXTRA PG"
        elif b > 0 and p == 0:
            faltando.append((model, b, p))
            status = "FALTANDO"
        elif p >= b:
            ok.append((model, b, p))
            status = "OK" if p == b else "OK+"
        else:
            parcial.append((model, b, p))
            pct = (p / b * 100) if b else 0
            status = f"PARCIAL {pct:.0f}%"

        if b == 0:
            vazio_backup.append(model)

        print(f"{model:<55} {b:>8} {p:>8}  {status}")

    total_b = sum(backup.values())
    total_p = sum(pg.get(m, 0) for m in backup)
    print("-" * 85)
    print(f"{'TOTAL (modelos no backup)':<55} {total_b:>8} {total_p:>8}")

    print("\n=== Resumo ===")
    print(f"  OK completos:     {len(ok)}")
    print(f"  Parciais:         {len(parcial)}")
    print(f"  Faltando (0):     {len(faltando)}")
    print(f"  Extra no Postgres:{len(so_pg)}")

    if faltando:
        print("\n--- Faltando importar ---")
        for model, b, p in sorted(faltando, key=lambda x: -x[1]):
            print(f"  {model}: backup={b}")

    if parcial:
        print("\n--- Importacao parcial ---")
        for model, b, p in sorted(parcial, key=lambda x: -x[1]):
            print(f"  {model}: {p}/{b}")

    # Apps no backup agrupados
    print("\n=== Por app (backup vs postgres) ===")
    apps_b: Counter = Counter()
    apps_p: Counter = Counter()
    for model, n in backup.items():
        apps_b[model.split(".")[0]] += n
    for model, n in pg.items():
        apps_p[model.split(".")[0]] += n
    for app in sorted(set(apps_b) | set(apps_p)):
        b = apps_b.get(app, 0)
        p = apps_p.get(app, 0)
        if b == 0 and p == 0:
            continue
        mark = "OK" if p >= b else ("FALTA" if p == 0 else "PARCIAL")
        print(f"  {app:<30} backup={b:>6}  postgres={p:>6}  [{mark}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
