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
    "regraConciliacao",
    "extrato_base",
    "notasfiscais",
    "notafiscalentrada",
    "contasapagar",
    "contasareceber",
    "regrarateio_lancamentos",
    "emprestimos",
    "OPCARTAO",
    "faturamento_medico",
    "servicos_medicos",
    "fluxo_de_caixa",
    "relatoriorecebiveis",
    "planejamento_orcamentario",
    "agendador_tarefas",
    "extrato_movimentos",
    "dashboard",
]


def _banco_ja_vazio(env: dict[str, str]) -> bool:
    code = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.contrib.auth.models import User
from empresa.models import Empresa
print(User.objects.count(), Empresa.objects.count())
"""
    out = subprocess.check_output(
        [sys.executable, "-c", code], env=env, cwd=ROOT, text=True
    ).strip()
    users, empresas = (int(x) for x in out.split())
    return users == 0 and empresas == 0


def _contagem_dados_usuario(env: dict[str, str]) -> int:
    code = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(
        '''
        SELECT COALESCE(SUM(n_live_tup), 0)::bigint
        FROM pg_stat_user_tables
        WHERE schemaname = current_schema()
          AND relname NOT IN (
              'django_migrations',
              'django_content_type',
              'auth_permission'
          )
        '''
    )
    print(int(cursor.fetchone()[0]))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return int(result.stdout.strip() or "0")


def _limpar_dados_postgres(env: dict[str, str]) -> None:
    if _banco_ja_vazio(env):
        print("banco sem dados de negocio — pulando truncate")
        return
    print("flush (limpar dados) ...")
    subprocess.check_call(
        [sys.executable, "manage.py", "flush", "--skip-checks", "--noinput"],
        env=env,
        cwd=ROOT,
    )


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
        elif app == "extrato":
            bucket = (
                "extrato_movimentos"
                if row["model"] == "extrato.extratomovimento"
                else "extrato_base"
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
    rows = _contagem_dados_usuario(env)
    if rows == 0:
        print("banco ja vazio — pulando truncate.")
    else:
        print(f"removendo ~{rows} registros existentes ...")
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
