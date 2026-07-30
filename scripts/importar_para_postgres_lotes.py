#!/usr/bin/env python
"""
Importa backup_render.json em lotes por app (mais seguro para arquivos grandes).
Requer DATABASE_URL no ambiente.

  set DATABASE_URL=postgresql://...
  python scripts/importar_para_postgres_lotes.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "backup_render.json"

# Ordem aproximada de dependencias entre apps Django
APP_ORDER = [
    "auth",
    "admin",
    "empresa",
    "socio",
    "usuario",
    "accounts",
    "categoria",
    "formapgto",
    "cobranca",
    "cliente",
    "fornecedor",
    "regrarateio",
    "regraImposto",
    "regraConciliacao",
    "contasapagar",
    "contasareceber",
    "extrato",
    "notasfiscais",
    "notafiscalentrada",
    "emprestimos",
    "OPCARTAO",
    "faturamento_medico",
    "servicos_medicos",
    "fluxo_de_caixa",
    "relatoriorecebiveis",
    "planejamento_orcamentario",
    "agendador_tarefas",
    "dashboard",
]


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL (External URL do financas-db no Render).", file=sys.stderr)
        return 1
    if not FIXTURE.is_file():
        print(f"Arquivo nao encontrado: {FIXTURE}", file=sys.stderr)
        return 1

    os.chdir(ROOT)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    print("migrate ...")
    subprocess.check_call(
        [sys.executable, "manage.py", "migrate", "--skip-checks", "--noinput"],
        env=env,
    )

    with FIXTURE.open(encoding="utf-8") as f:
        rows = json.load(f)

    by_app: dict[str, list] = defaultdict(list)
    for row in rows:
        app = row["model"].split(".", 1)[0]
        by_app[app].append(row)

    ordered_apps = [a for a in APP_ORDER if a in by_app]
    ordered_apps += sorted(set(by_app) - set(ordered_apps))

    print(f"Total registros: {len(rows)} em {len(by_app)} apps")
    tmpdir = Path(tempfile.mkdtemp(prefix="sfp_import_"))

    try:
        for app in ordered_apps:
            chunk = by_app[app]
            path = tmpdir / f"{app}.json"
            path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"loaddata {app} ({len(chunk)} registros) ...")
            subprocess.check_call(
                [sys.executable, "manage.py", "loaddata", "--skip-checks", str(path)],
                env=env,
            )
    finally:
        for p in tmpdir.glob("*.json"):
            p.unlink(missing_ok=True)
        tmpdir.rmdir()

    print("Importacao por lotes concluida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
