#!/usr/bin/env python
"""
Importa dados do SQLite local para PostgreSQL (DATABASE_URL).

Importa somente modelos em que SQLite > Postgres (ignora tabelas Django internas).

  set DATABASE_URL=postgresql://...
  python scripts/importar_sqlite_para_postgres.py
  python scripts/importar_sqlite_para_postgres.py --dry-run
  python scripts/importar_sqlite_para_postgres.py --only relatoriorecebiveis
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Ordem respeitando FKs
MODELS_ORDER = [
    "planejamento_orcamentario.itemorcamento",
    "planejamento_orcamentario.lancamentoorcamento",
    "extrato.extratomovimento",
    "faturamento_medico.medcloudconfig",
    "faturamento_medico.medcloudconvenioparceiro",
    "OPCARTAO.cartaocredito",
    "OPCARTAO.faturacartaocredito",
    "OPCARTAO.itemfaturacartao",
    "relatoriorecebiveis.relatoriorecebiveismaquinacartao",
    "notasfiscais.notafiscalservico",
    "notasfiscais.apuracaoperiodo",
    "notasfiscais.lognotafiscal",
    "notafiscalentrada.notafiscalentrada",
    "notafiscalentrada.notafiscalentradaitem",
]

SKIP_PREFIXES = ("django_",)

EXPORT_CODE = r"""
import json, os, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
MODELS = json.loads(sys.argv[2])
OUT = Path(sys.argv[3])
ONLY = json.loads(sys.argv[4])

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

import django
django.setup()

from django.apps import apps
from django.core import serializers

OUT.mkdir(parents=True, exist_ok=True)
summary = {}

for label in MODELS:
    if ONLY and label not in ONLY:
        continue
    app, name = label.split(".", 1)
    model = apps.get_model(app, name)
    qs = model.objects.all().order_by("pk")
    rows = json.loads(serializers.serialize("json", qs))
    path = OUT / f"{app}_{name}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary[label] = len(rows)
    print(f"export {label}: {len(rows)}")

(Path(OUT) / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
"""

IMPORT_CODE = r"""
import json, os, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
INDIR = Path(sys.argv[2])
MODELS = json.loads(sys.argv[3])
ONLY = json.loads(sys.argv[4])
CHUNK = int(sys.argv[5])

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

import django
django.setup()

from django.apps import apps
from django.core import serializers
from django.db import IntegrityError, transaction

totals = {"ok": 0, "skip": 0, "err": 0}

for label in MODELS:
    if ONLY and label not in ONLY:
        continue
    app, name = label.split(".", 1)
    path = INDIR / f"{app}_{name}.json"
    if not path.is_file():
        print(f"skip {label}: arquivo ausente")
        continue
    rows = json.loads(path.read_text(encoding="utf-8"))
    model = apps.get_model(app, name)
    pg_pks = set(model.objects.values_list("pk", flat=True))
    missing = [r for r in rows if r.get("pk") not in pg_pks]
    if not missing:
        print(f"import {label}: ja completo ({len(rows)} registros)")
        continue
    before = model.objects.count()
    ok = skip = err = 0
    for i in range(0, len(missing), CHUNK):
        chunk = missing[i : i + CHUNK]
        payload = json.dumps(chunk)
        try:
            with transaction.atomic():
                for obj in serializers.deserialize("json", payload):
                    obj.save()
            ok += len(chunk)
        except IntegrityError:
            for row in chunk:
                try:
                    with transaction.atomic():
                        for obj in serializers.deserialize("json", json.dumps([row])):
                            obj.save()
                    ok += 1
                except IntegrityError:
                    skip += 1
                except Exception as exc:
                    err += 1
                    if err <= 3:
                        print(f" ERRO {label} pk={row.get('pk')}: {exc}")
        except Exception as exc:
            err += len(chunk)
            print(f" ERRO lote {label}: {exc}")
    after = model.objects.count()
    print(f"import {label}: +{after-before} (ok~{ok} skip={skip} err={err}) total={after}")
    totals["ok"] += ok
    totals["skip"] += skip
    totals["err"] += err

print(f"TOTAL ok~={totals['ok']} skip={totals['skip']} err={totals['err']}")
"""

COUNT_CODE = r"""
import json, os, sys
from pathlib import Path

MODELS = json.loads(sys.argv[1])
use_pg = sys.argv[2] == "pg"

if use_pg:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
    import django
    django.setup()
    from django.apps import apps
    counts = {}
    for label in MODELS:
        app, name = label.split(".", 1)
        model = apps.get_model(app, name)
        counts[label] = model.objects.count()
else:
    import sqlite3
    from django.apps import apps
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
    import django
    django.setup()
    counts = {}
    for label in MODELS:
        app, name = label.split(".", 1)
        model = apps.get_model(app, name)
        counts[label] = model.objects.count()

print(json.dumps(counts))
"""


def _counts(models: list[str], pg: bool, env: dict) -> dict[str, int]:
    run_env = env.copy()
    if not pg:
        run_env.pop("DATABASE_URL", None)
    out = subprocess.check_output(
        [sys.executable, "-c", COUNT_CODE, json.dumps(models), "pg" if pg else "sq"],
        env=run_env,
        cwd=ROOT,
        text=True,
    )
    return json.loads(out.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", action="append", default=[], help="Modelo app.model (pode repetir)")
    parser.add_argument("--chunk", type=int, default=100)
    args = parser.parse_args()

    if not (ROOT / "db.sqlite3").is_file():
        print("db.sqlite3 não encontrado.", file=sys.stderr)
        return 1

    env = os.environ.copy()
    if not env.get("DATABASE_URL"):
        url_file = ROOT / "render_db.url"
        if url_file.is_file():
            env["DATABASE_URL"] = url_file.read_text(encoding="utf-8").strip()
    if not env.get("DATABASE_URL") and not args.dry_run:
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 1

    only = args.only or []
    models = [m for m in MODELS_ORDER if not only or m in only]

    print("=== Contagens SQLite vs Postgres ===")
    sq = _counts(models, pg=False, env=env)
    pg = _counts(models, pg=True, env=env) if env.get("DATABASE_URL") else {}

    to_import = []
    for label in models:
        s, p = sq.get(label, 0), pg.get(label, 0)
        mark = "OK" if s == p else ("IMPORTAR" if s > p else "PG+")
        print(f"  {label}: sqlite={s} postgres={p} [{mark}]")
        if s > p:
            to_import.append(label)

    if not to_import:
        print("\nNada a importar — Postgres >= SQLite em todos os modelos listados.")
        return 0

    if args.dry_run:
        print(f"\n(dry-run) Importaria: {', '.join(to_import)}")
        return 0

    models_json = json.dumps(models)
    only_json = json.dumps(only)
    tmpdir = Path(tempfile.mkdtemp(prefix="sfp_sqlite_export_"))

    print("\n=== Exportando do SQLite ===")
    export_env = env.copy()
    export_env.pop("DATABASE_URL", None)
    subprocess.check_call(
        [sys.executable, "-c", EXPORT_CODE, str(ROOT), models_json, str(tmpdir), only_json],
        env=export_env,
        cwd=ROOT,
    )

    print("\n=== Importando no PostgreSQL ===")
    subprocess.check_call(
        [
            sys.executable,
            "-c",
            IMPORT_CODE,
            str(ROOT),
            str(tmpdir),
            models_json,
            only_json,
            str(args.chunk),
        ],
        env=env,
        cwd=ROOT,
    )

    print("\n=== Corrigindo sequências PostgreSQL ===")
    env["PYTHONPATH"] = str(ROOT)
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "corrigir_sequencias_postgres.py")],
        env=env,
        cwd=ROOT,
    )

    print("\n=== Verificação final ===")
    pg2 = _counts(models, pg=True, env=env)
    for label in models:
        s, p = sq.get(label, 0), pg2.get(label, 0)
        ok = "OK" if s == p else f"FALTA {s-p}"
        print(f"  {label}: sqlite={s} postgres={p} [{ok}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
