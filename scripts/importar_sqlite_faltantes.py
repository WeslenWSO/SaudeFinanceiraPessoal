#!/usr/bin/env python
"""
Importa do SQLite local para PostgreSQL (DATABASE_URL):

  - planejamento_orcamentario.itemorcamento + lancamentoorcamento
  - extrato.extratomovimento
  - faturamento_medico.medcloudconfig + medcloudconvenioparceiro

  set DATABASE_URL=postgresql://...
  python scripts/importar_sqlite_faltantes.py
  python scripts/importar_sqlite_faltantes.py --dry-run
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

MODELS = [
    "planejamento_orcamentario.itemorcamento",
    "planejamento_orcamentario.lancamentoorcamento",
    "extrato.extratomovimento",
    "faturamento_medico.medcloudconfig",
    "faturamento_medico.medcloudconvenioparceiro",
]

EXPORT_CODE = r"""
import json, os, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
MODELS = json.loads(sys.argv[2])
OUT = Path(sys.argv[3])

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

import django
django.setup()

from django.apps import apps
from django.core import serializers

OUT.mkdir(parents=True, exist_ok=True)
summary = {}

for label in MODELS:
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

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

import django
django.setup()

from django.apps import apps
from django.core import serializers
from django.db import IntegrityError, transaction

totals = {"ok": 0, "skip": 0, "err": 0}

for label in MODELS:
    app, name = label.split(".", 1)
    path = INDIR / f"{app}_{name}.json"
    if not path.is_file():
        print(f"skip {label}: arquivo ausente")
        continue
    rows = json.loads(path.read_text(encoding="utf-8"))
    model = apps.get_model(app, name)
    before = model.objects.count()
    ok = skip = err = 0
    for row in rows:
        payload = json.dumps([row])
        try:
            with transaction.atomic():
                for obj in serializers.deserialize("json", payload):
                    obj.save()
            ok += 1
        except IntegrityError:
            skip += 1
        except Exception as exc:
            err += 1
            if err <= 3:
                print(f" ERRO {label} pk={row.get('pk')}: {exc}")
    after = model.objects.count()
    print(f"import {label}: +{after-before} (ok={ok} skip={skip} err={err}) total={after}")
    totals["ok"] += ok
    totals["skip"] += skip
    totals["err"] += err

print(f"TOTAL ok={totals['ok']} skip={totals['skip']} err={totals['err']}")
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
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

    models_json = json.dumps(MODELS)
    tmpdir = Path(tempfile.mkdtemp(prefix="sfp_sqlite_export_"))

    print("=== Exportando do SQLite ===")
    export_env = env.copy()
    export_env.pop("DATABASE_URL", None)
    subprocess.check_call(
        [sys.executable, "-c", EXPORT_CODE, str(ROOT), models_json, str(tmpdir)],
        env=export_env,
        cwd=ROOT,
    )

    summary_path = tmpdir / "_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        print("\nResumo export:")
        for k, v in summary.items():
            print(f"  {k}: {v}")

    if args.dry_run:
        print("\n(dry-run — importação não executada)")
        return 0

    print("\n=== Importando no PostgreSQL ===")
    subprocess.check_call(
        [sys.executable, "-c", IMPORT_CODE, str(ROOT), str(tmpdir), models_json],
        env=env,
        cwd=ROOT,
    )

    # Verificação final
    verify_env = env.copy()
    subprocess.check_call(
        [
            sys.executable,
            "-c",
            """
import os, django, json, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE','SaudeFinanceira.settings')
django.setup()
from planejamento_orcamentario.models import LancamentoOrcamento, ItemOrcamento
from extrato.models import ExtratoMovimento
from faturamento_medico.models import MedcloudConfig, MedcloudConvenioParceiro
print('POSTGRES FINAL:')
print(' ItemOrcamento', ItemOrcamento.objects.count())
print(' LancamentoOrcamento', LancamentoOrcamento.objects.count())
print(' ExtratoMovimento', ExtratoMovimento.objects.count())
print(' MedcloudConfig', MedcloudConfig.objects.count())
print(' MedcloudConvenioParceiro', MedcloudConvenioParceiro.objects.count())
""",
        ],
        env=verify_env,
        cwd=ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
