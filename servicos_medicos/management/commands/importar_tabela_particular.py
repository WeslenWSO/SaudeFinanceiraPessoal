"""Importa preços RX na TABELA PARTICULAR (empresa 1)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


def _load_particular_script():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "importar_tabela_preco_particular.py"
    spec = importlib.util.spec_from_file_location("importar_tabela_preco_particular", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(root))
    spec.loader.exec_module(module)
    return module


class Command(BaseCommand):
    help = (
        "Cadastra serviços RX e preços em scripts/dados/tabela_preco_particular_rx.tsv "
        "no convênio/cabeçalho TABELA PARTICULAR (empresa 1)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--somente-novos", action="store_true")
        parser.add_argument("--empresa-id", type=int, default=1)
        parser.add_argument("--convenio", default="PARTICULAR")
        parser.add_argument("--cabecalho", default="TABELA PARTICULAR")
        parser.add_argument("--arquivo", type=Path, default=None)

    def handle(self, *args, **options):
        mod = _load_particular_script()
        root = Path(__file__).resolve().parents[3]
        arquivo = options["arquivo"] or mod.TSV_DEFAULT
        if not arquivo.is_absolute():
            arquivo = root / arquivo

        args = mod.build_args(
            dry_run=options["dry_run"],
            arquivo=arquivo,
            empresa_id=options["empresa_id"],
            convenio=options["convenio"],
            cabecalho=options["cabecalho"],
            somente_novos=options["somente_novos"],
        )
        code = mod.run_import(args, skip_db_url_check=True)
        if code:
            self.stderr.write(self.style.ERROR(f"Importação encerrada com código {code}."))
        else:
            self.stdout.write(self.style.SUCCESS("Importação concluída."))
        return code
