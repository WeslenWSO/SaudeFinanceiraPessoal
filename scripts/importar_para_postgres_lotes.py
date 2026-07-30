#!/usr/bin/env python
"""
Importa backup_render.json em lotes por app (mais seguro para arquivos grandes).
Suporta retomada apos queda de conexao (--resume).

  set DATABASE_URL=postgresql://...
  python scripts/importar_para_postgres_lotes.py
  python scripts/importar_para_postgres_lotes.py --resume
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "backup_render.json"
PROGRESS_FILE = ROOT / "import_progress.json"
CHUNK_SIZE = 250
MAX_RETRIES = 5
RETRY_SLEEP = 15

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


def _load_progress() -> set[str]:
    if not PROGRESS_FILE.is_file():
        return set()
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return set(data.get("done_apps", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_progress(done_apps: set[str]) -> None:
    PROGRESS_FILE.write_text(
        json.dumps({"done_apps": sorted(done_apps)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    out = subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip()
    users, empresas = (int(x) for x in out.split())
    return users == 0 and empresas == 0


def _limpar_contasareceber_parcial(env: dict[str, str]) -> None:
    code = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(
        '''
        TRUNCATE TABLE
            contasareceber_baixacontaareceber,
            contasareceber_contaareceber
        RESTART IDENTITY CASCADE
        '''
    )
print("contasareceber limpo")
"""
    subprocess.check_call([sys.executable, "-c", code], env=env)


def _limpar_extrato_parcial(env: dict[str, str]) -> None:
    code = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(
        '''
        TRUNCATE TABLE
            extrato_extratomovimento,
            extrato_lancamento,
            extrato_conciliacao,
            extrato_extratoarquivo,
            extrato_contabancaria,
            extrato_banco
        RESTART IDENTITY CASCADE
        '''
    )
print("extrato limpo")
"""
    subprocess.check_call([sys.executable, "-c", code], env=env)


def _limpar_dados_postgres(env: dict[str, str]) -> None:
    if _banco_ja_vazio(env):
        print("banco sem dados de negocio — pulando limpeza")
        return
    print("flush (limpar dados) ...")
    subprocess.check_call(
        [sys.executable, "manage.py", "flush", "--skip-checks", "--noinput"],
        env=env,
    )


def _loaddata(path: Path, env: dict[str, str], label: str) -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            subprocess.check_call(
                [sys.executable, "manage.py", "loaddata", "--skip-checks", str(path)],
                env=env,
            )
            return
        except subprocess.CalledProcessError:
            if attempt >= MAX_RETRIES:
                raise
            print(f"  falha em {label} (tentativa {attempt}/{MAX_RETRIES}) — aguardando {RETRY_SLEEP}s ...")
            time.sleep(RETRY_SLEEP)


def _chunks(rows: list[dict], size: int) -> list[list[dict]]:
    if len(rows) <= size:
        return [rows]
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retoma importacao (nao apaga dados; pula apps ja concluidos).",
    )
    args = parser.parse_args()

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

    done_apps = _load_progress() if args.resume else set()

    print("migrate ...")
    subprocess.check_call(
        [sys.executable, "manage.py", "migrate", "--skip-checks", "--noinput"],
        env=env,
    )

    if args.resume:
        print(f"retomando — {len(done_apps)} apps ja importados")
    else:
        print("limpar dados ...")
        _limpar_dados_postgres(env)
        done_apps = set()
        if PROGRESS_FILE.is_file():
            PROGRESS_FILE.unlink()

    with FIXTURE.open(encoding="utf-8") as f:
        rows = json.load(f)

    by_app: dict[str, list] = defaultdict(list)
    for row in rows:
        app = row["model"].split(".", 1)[0]
        by_app[app].append(row)

    regra_rows = by_app.pop("regrarateio", [])
    if regra_rows:
        by_app["regrarateio_base"] = [
            r for r in regra_rows if r["model"] != "regrarateio.lancamentorateio"
        ]
        by_app["regrarateio_lancamentos"] = [
            r for r in regra_rows if r["model"] == "regrarateio.lancamentorateio"
        ]

    extrato_rows = by_app.pop("extrato", [])
    if extrato_rows:
        by_app["extrato_base"] = [
            r for r in extrato_rows if r["model"] != "extrato.extratomovimento"
        ]
        by_app["extrato_movimentos"] = [
            r for r in extrato_rows if r["model"] == "extrato.extratomovimento"
        ]

    ordered_apps = [a for a in APP_ORDER if a in by_app]
    ordered_apps += sorted(set(by_app) - set(ordered_apps))

    print(f"Total registros: {len(rows)} em {len(by_app)} apps")
    tmpdir = Path(tempfile.mkdtemp(prefix="sfp_import_"))

    try:
        for app in ordered_apps:
            if app in done_apps:
                print(f"pulando {app} (ja importado)")
                continue

            if app == "extrato_base" and "extrato_base" not in done_apps:
                print("limpando extrato parcial (se houver) ...")
                _limpar_extrato_parcial(env)

            if app == "contasareceber" and "contasareceber" not in done_apps:
                print("limpando contasareceber parcial (se houver) ...")
                _limpar_contasareceber_parcial(env)

            chunk = by_app[app]
            parts = _chunks(chunk, CHUNK_SIZE)
            print(f"loaddata {app} ({len(chunk)} registros, {len(parts)} lote(s)) ...")

            for idx, part in enumerate(parts, start=1):
                suffix = f"_{idx}" if len(parts) > 1 else ""
                path = tmpdir / f"{app}{suffix}.json"
                path.write_text(json.dumps(part, ensure_ascii=False, indent=2), encoding="utf-8")
                label = f"{app}{suffix}"
                print(f"  lote {idx}/{len(parts)} ({len(part)} registros) ...")
                _loaddata(path, env, label)

            done_apps.add(app)
            _save_progress(done_apps)
            print(f"  ok: {app}")
    finally:
        for p in tmpdir.glob("*.json"):
            p.unlink(missing_ok=True)
        tmpdir.rmdir()

    if PROGRESS_FILE.is_file():
        PROGRESS_FILE.unlink()
    print("Importacao por lotes concluida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
