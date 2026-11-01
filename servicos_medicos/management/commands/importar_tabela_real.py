"""Importa preços na TABELA - REAL (convênio REAL CONVÊNIOS, empresa 1)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


def _load_real_script():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "importar_tabela_preco_real.py"
    spec = importlib.util.spec_from_file_location("importar_tabela_preco_real", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(root))
    spec.loader.exec_module(module)
    return module


class Command(BaseCommand):
    help = (
        "Cadastra/atualiza serviços e preços no convênio REAL CONVÊNIOS, "
        "cabeçalho TABELA - REAL (RX, US, TC, RM, etc.)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--somente-novos", action="store_true")
        parser.add_argument("--empresa-id", type=int, default=1)
        parser.add_argument("--convenio", default="REAL CONVÊNIOS")
        parser.add_argument("--cabecalho", default="TABELA - REAL")
        parser.add_argument(
            "modalidades",
            nargs="*",
            help="Opcional: rx us tc rm mammo eg ecg",
        )

    def handle(self, *args, **options):
        mod = _load_real_script()
        argv: list[str] = []
        if options["dry_run"]:
            argv.append("--dry-run")
        if options["somente_novos"]:
            argv.append("--somente-novos")
        argv.extend(["--empresa-id", str(options["empresa_id"])])
        argv.extend(["--convenio", options["convenio"]])
        argv.extend(["--cabecalho", options["cabecalho"]])
        argv.extend(options["modalidades"] or [])

        code = mod.main(argv)
        if code:
            self.stderr.write(self.style.ERROR("Importação REAL encerrada com erros."))
        else:
            self.stdout.write(self.style.SUCCESS("Importação REAL concluída."))
        return code
