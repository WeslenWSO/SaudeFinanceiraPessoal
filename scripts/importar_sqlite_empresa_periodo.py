#!/usr/bin/env python
"""
Importa do SQLite local para PostgreSQL registros faltantes de uma empresa,
a partir de uma data (inclusive).

Uso:
  python scripts/importar_sqlite_empresa_periodo.py --empresa-id 19 --desde 2026-08-30
  python scripts/importar_sqlite_empresa_periodo.py --empresa "R S NOBRE" --desde 2026-08-30 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Ordem respeitando FKs
MODELS_ORDER = [
    "categoria.categoria",
    "planejamento_orcamentario.itemorcamento",
    "planejamento_orcamentario.lancamentoorcamento",
    "contasareceber.contaareceber",
    "contasapagar.contasapagar",
    "notasfiscais.notafiscalservico",
    "faturamento_medico.faturamentomedico",
    "extrato.lancamento",
    "extrato.extratomovimento",
]

DATE_FIELDS = {
    "categoria.categoria": None,  # importa todas da empresa (FK)
    "planejamento_orcamentario.itemorcamento": "data_inicio",
    "planejamento_orcamentario.lancamentoorcamento": "data_lancamento",
    "contasareceber.contaareceber": ["data_emissao", "data_vencimento", "data_recebimento"],
    "contasapagar.contasapagar": ["dtEmissao", "dtvenc", "dtPag"],
    "notasfiscais.notafiscalservico": "data_emissao",
    "faturamento_medico.faturamentomedico": "data",
    "extrato.lancamento": "data",
    "extrato.extratomovimento": "data_baixa",
}

EXPORT_FILTER_CODE = r"""
import json, os, sys, sqlite3
from pathlib import Path
from datetime import date

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
CONFIG = json.loads(sys.argv[3])

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

import django
django.setup()

from django.apps import apps
from django.core import serializers
from django.db.models import Q

empresa_id = CONFIG["empresa_id"]
desde = date.fromisoformat(CONFIG["desde"])
models = CONFIG["models"]
date_fields = CONFIG["date_fields"]

OUT.mkdir(parents=True, exist_ok=True)
summary = {}

def _filter_qs(model, label):
    qs = model.objects.filter(empresa_id=empresa_id)
    field = date_fields.get(label)
    if field is None:
        return qs
    if isinstance(field, list):
        q = Q()
        for f in field:
            q |= Q(**{f"{f}__gte": desde})
        return qs.filter(q)
    return qs.filter(**{f"{field}__gte": desde})

for label in models:
    app, name = label.split(".", 1)
    model = apps.get_model(app, name)
    try:
        qs = _filter_qs(model, label).order_by("pk")
    except Exception as exc:
        print(f"export {label}: ERRO filtro — {exc}")
        summary[label] = 0
        continue
    rows = json.loads(serializers.serialize("json", qs))
    path = OUT / f"{app}_{name}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary[label] = len(rows)
    print(f"export {label}: {len(rows)}")

(OUT / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
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
    pg_pks = set(model.objects.values_list("pk", flat=True))
    missing = [r for r in rows if r.get("pk") not in pg_pks]
    if not missing:
        print(f"import {label}: ja completo ({len(rows)} registros)")
        continue
    before = model.objects.count()
    ok = skip = err = 0
    for row in missing:
        payload = json.dumps([row])
        try:
            with transaction.atomic():
                for obj in serializers.deserialize("json", payload):
                    obj.save()
            ok += 1
        except IntegrityError as exc:
            skip += 1
            if skip <= 3:
                print(f" skip {label} pk={row.get('pk')}: {exc}")
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


def _resolve_empresa_id(empresa_id: int | None, empresa_nome: str | None, env: dict) -> int:
    if empresa_id:
        return empresa_id
    if not empresa_nome:
        raise ValueError("Informe --empresa-id ou --empresa")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
    import django
    django.setup()
    from empresa.models import Empresa
    qs = Empresa.objects.filter(razao__icontains=empresa_nome.strip())
    if qs.count() != 1:
        nomes = list(qs.values_list("id", "razao"))
        raise ValueError(f"Empresa ambígua ou não encontrada: {nomes}")
    return qs.first().pk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", type=int)
    parser.add_argument("--empresa", help="Parte do nome/razão social")
    parser.add_argument("--desde", required=True, help="Data ISO YYYY-MM-DD")
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

    try:
        empresa_id = _resolve_empresa_id(args.empresa_id, args.empresa, env)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    desde = date.fromisoformat(args.desde)
    config = {
        "empresa_id": empresa_id,
        "desde": desde.isoformat(),
        "models": MODELS_ORDER,
        "date_fields": DATE_FIELDS,
    }

    tmpdir = Path(tempfile.mkdtemp(prefix="sfp_empresa_export_"))
    print(f"=== Exportando SQLite — empresa_id={empresa_id} desde {desde.isoformat()} ===")
    export_env = env.copy()
    export_env.pop("DATABASE_URL", None)
    export_env["PYTHONPATH"] = str(ROOT)
    subprocess.check_call(
        [sys.executable, "-c", EXPORT_FILTER_CODE, str(ROOT), str(tmpdir), json.dumps(config)],
        env=export_env,
        cwd=ROOT,
    )

    summary_path = tmpdir / "_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        total = sum(summary.values())
        print("\nResumo export:")
        for k, v in summary.items():
            if v:
                print(f"  {k}: {v}")
        if total == 0:
            print("Nenhum registro encontrado no SQLite para importar.")
            return 0

    if args.dry_run:
        print("\n(dry-run — importação não executada)")
        return 0

    print("\n=== Importando no PostgreSQL ===")
    env["PYTHONPATH"] = str(ROOT)
    subprocess.check_call(
        [sys.executable, "-c", IMPORT_CODE, str(ROOT), str(tmpdir), json.dumps(MODELS_ORDER)],
        env=env,
        cwd=ROOT,
    )

    print("\n=== Corrigindo sequências PostgreSQL ===")
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "corrigir_sequencias_postgres.py")],
        env=env,
        cwd=ROOT,
    )

    print("\n=== Verificação ===")
    verify_env = env.copy()
    subprocess.check_call(
        [
            sys.executable,
            "-c",
            f"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','SaudeFinanceira.settings')
django.setup()
from categoria.models import Categoria
from planejamento_orcamentario.models import ItemOrcamento, LancamentoOrcamento
eid = {empresa_id}
desde = '{desde.isoformat()}'
print('Categoria:', Categoria.objects.filter(empresa_id=eid).count())
print('ItemOrcamento:', ItemOrcamento.objects.filter(empresa_id=eid).count())
print('LancamentoOrcamento >= desde:', LancamentoOrcamento.objects.filter(empresa_id=eid, data_lancamento__gte=desde).count())
""",
        ],
        env=verify_env,
        cwd=ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
