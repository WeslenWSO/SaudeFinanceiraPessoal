"""Importa preços RX na TABELA PARTICULAR (empresa 1)."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Cadastra serviços e preços a partir de scripts/dados/tabela_preco_particular_rx.tsv "
        "(convênio/cabeçalho PARTICULAR)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--somente-novos", action="store_true")
        parser.add_argument("--empresa-id", type=int, default=1)
        parser.add_argument("--convenio", default="PARTICULAR")
        parser.add_argument("--cabecalho", default="TABELA PARTICULAR")
        parser.add_argument(
            "--arquivo",
            type=Path,
            default=None,
            help="TSV alternativo (codigo, nome, valor)",
        )

    def handle(self, *args, **options):
        root = Path(__file__).resolve().parents[3]
        script = root / "scripts" / "importar_tabela_preco_particular.py"
        if not script.is_file():
            self.stderr.write(f"Script não encontrado: {script}")
            return 1

        cmd = [sys.executable, str(script)]
        if options["dry_run"]:
            cmd.append("--dry-run")
        if options["somente_novos"]:
            cmd.append("--somente-novos")
        cmd.extend(["--empresa-id", str(options["empresa_id"])])
        cmd.extend(["--convenio", options["convenio"]])
        cmd.extend(["--cabecalho", options["cabecalho"]])
        if options["arquivo"]:
            cmd.extend(["--arquivo", str(options["arquivo"])])

        env = os.environ.copy()
        if not env.get("DATABASE_URL") and (root / "render_db.url").is_file():
            env["DATABASE_URL"] = (root / "render_db.url").read_text(encoding="utf-8").strip()

        result = subprocess.run(cmd, cwd=str(root), env=env)
        return result.returncode
