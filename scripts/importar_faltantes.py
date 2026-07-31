#!/usr/bin/env python
"""
Importa apenas apps com dados faltando ou parciais (backup vs PostgreSQL).

  set DATABASE_URL=postgresql://...
  python scripts/importar_faltantes.py
  python scripts/importar_faltantes.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "backup_render.json"
IMPORT_SCRIPT = ROOT / "scripts" / "importar_para_postgres_lotes.py"

SKIP_APPS = {"admin", "sessions", "contenttypes"}

sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

APP_ORDER = [
    "auth",
    "admin",
    "sessions",
    "empresa",
    "socio",
    "usuario",
    "accounts",
    "categoria",
    "formapgto",
    "cobranca",
    "cliente",
    "fornecedor",
    "regrarateio_base",
    "regraImposto",
    "regraConciliacao",
    "extrato_base",
    "notasfiscais",
    "notafiscalentrada",
    "contasapagar",
    "contasareceber",
    "regrarateio_lancamentos",
    "emprestimos",
    "OPCARTAO",
    "servicos_medicos",
    "faturamento_medico",
    "fluxo_de_caixa",
    "relatoriorecebiveis",
    "planejamento_orcamentario",
    "agendador_tarefas",
    "extrato_movimentos",
    "dashboard",
]

BUCKET_TO_APP = {
    "regrarateio_base": "regrarateio",
    "regrarateio_lancamentos": "regrarateio",
    "extrato_base": "extrato",
    "extrato_movimentos": "extrato",
}

REIMPORT_IF_PARTIAL = frozenset({
    "notasfiscais",
    "faturamento_medico",
    "contasareceber",
    "extrato",
    "regrarateio",
})

SKIP_PARTIAL_SMALL = frozenset({"empresa", "auth"})


def _backup_by_app() -> Counter:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_app: dict[str, int] = defaultdict(int)
    for row in rows:
        app = row["model"].split(".", 1)[0]
        by_app[app] += 1
    return Counter(by_app)


def _postgres_by_app() -> Counter:
    import django

    django.setup()
    from django.apps import apps

    by_app: dict[str, int] = defaultdict(int)
    for model in apps.get_models():
        label = model._meta.app_label
        if label in SKIP_APPS:
            continue
        try:
            n = model.objects.count()
        except Exception:
            continue
        if n:
            by_app[label] += n
    return Counter(by_app)


def _apps_faltantes() -> list[str]:
    backup = _backup_by_app()
    pg = _postgres_by_app()
    pg_norm = Counter(pg)

    faltando: list[str] = []
    for app in APP_ORDER:
        if app in SKIP_APPS or app in {"regrarateio_base", "extrato_base"}:
            continue
        b_key = BUCKET_TO_APP.get(app, app)
        b = backup.get(b_key, 0)
        if b == 0:
            continue
        p = pg_norm.get(b_key, 0)
        if p == 0:
            faltando.append(app)
        elif p < b:
            if b_key in SKIP_PARTIAL_SMALL:
                continue
            if b_key in REIMPORT_IF_PARTIAL or app in REIMPORT_IF_PARTIAL:
                faltando.append(app)
    return faltando


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="So lista apps faltantes.")
    parser.add_argument("--chunk-size", type=int, default=500)
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 1
    if not FIXTURE.is_file():
        print(f"Arquivo nao encontrado: {FIXTURE}", file=sys.stderr)
        return 1

    apps = _apps_faltantes()
    if not apps:
        print("Nada faltando — Postgres >= backup em todos os apps.")
        return 0

    print("Apps a importar (ordem):")
    for app in apps:
        print(f"  - {app}")

    if args.dry_run:
        return 0

    cmd = [sys.executable, str(IMPORT_SCRIPT), "--chunk-size", str(args.chunk_size)]
    for app in apps:
        cmd.extend(["--only", app])

    print("\nExecutando importacao sequencial ...")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
