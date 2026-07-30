#!/usr/bin/env python
"""
Importa backup_render.json inteiro para PostgreSQL (loaddata unico).
Ordena registros por dependencia antes de carregar.

  set DATABASE_URL=postgresql://...
  python scripts/importar_postgres_completo.py
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
URL_FILE = ROOT / "render_db.url"

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
    "extrato",
    "regraConciliacao",
    "contasapagar",
    "contasareceber",
    "regrarateio_lancamentos",
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


def _limpar_dados_postgres(env: dict[str, str]) -> None:
    code = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(
        '''
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (
                SELECT tablename FROM pg_tables
                WHERE schemaname = current_schema()
                  AND tablename NOT IN (
                      'django_migrations',
                      'django_content_type',
                      'auth_permission'
                  )
            ) LOOP
                EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
            END LOOP;
        END $$;
        '''
    )
print("truncate cascade ok")
"""
    subprocess.check_call([sys.executable, "-c", code], env=env, cwd=ROOT)


def _ordenar_fixture(rows: list[dict]) -> list[dict]:
    by_app: dict[str, list] = defaultdict(list)
    for row in rows:
        app = row["model"].split(".", 1)[0]
        if app == "regrarateio":
            bucket = (
                "regrarateio_lancamentos"
                if row["model"] == "regrarateio.lancamentorateio"
                else "regrarateio_base"
            )
            by_app[bucket].append(row)
        else:
            by_app[app].append(row)

    ordered_apps = [a for a in APP_ORDER if a in by_app]
    ordered_apps += sorted(set(by_app) - set(ordered_apps))

    ordered: list[dict] = []
    for app in ordered_apps:
        ordered.extend(by_app[app])
    return ordered


def main() -> int:
    if not os.environ.get("DATABASE_URL") and URL_FILE.is_file():
        os.environ["DATABASE_URL"] = URL_FILE.read_text(encoding="utf-8").strip()

    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL (External URL do financas-db no Render).", file=sys.stderr)
        return 1
    if not FIXTURE.is_file():
        print(f"Arquivo nao encontrado: {FIXTURE}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    print("migrate ...")
    subprocess.check_call(
        [sys.executable, "manage.py", "migrate", "--skip-checks", "--noinput"],
        env=env,
        cwd=ROOT,
    )

    print("limpar dados (truncate cascade) ...")
    _limpar_dados_postgres(env)

    with FIXTURE.open(encoding="utf-8") as f:
        rows = json.load(f)

    ordered = _ordenar_fixture(rows)
    print(f"ordenando {len(ordered)} registros por dependencia ...")

    tmp = Path(tempfile.mkstemp(prefix="sfp_sorted_", suffix=".json")[1])
    try:
        tmp.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"loaddata (pode levar varios minutos) ...")
        subprocess.check_call(
            [sys.executable, "manage.py", "loaddata", "--skip-checks", str(tmp)],
            env=env,
            cwd=ROOT,
        )
    finally:
        tmp.unlink(missing_ok=True)

    print("Importacao concluida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
