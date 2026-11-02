#!/usr/bin/env python
"""
Apaga linhas de TabelaPreco pelos ids de Cabeçalho (funciona sem deploy do manage.py).

  python scripts/apagar_tabela_preco_por_id.py --listar
  python scripts/apagar_tabela_preco_por_id.py --id 6 --id 8 --dry-run
  python scripts/apagar_tabela_preco_por_id.py --id 6 --id 8 --confirmar

Referência Medicinarte: ABDES id 6, JARDEL id 7 (confira com --listar).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
if not os.environ.get("DATABASE_URL", "").strip():
    _render_db = ROOT / "render_db.url"
    if _render_db.is_file():
        os.environ["DATABASE_URL"] = _render_db.read_text(encoding="utf-8").strip()


def _setup_django():
    import django

    django.setup()


def listar(empresa_id: int) -> None:
    from servicos_medicos.models import Cabecalho, TabelaPreco

    qs = (
        Cabecalho.objects.filter(empresa_id=empresa_id)
        .select_related("convenio")
        .order_by("convenio__nome", "nome_tabela")
    )
    if not qs.exists():
        print(f"Nenhum cabeçalho para empresa_id={empresa_id}.")
        return
    print(f"Cabeçalhos (empresa_id={empresa_id}):")
    for cab in qs:
        n = TabelaPreco.objects.filter(cabecalho_id=cab.pk).count()
        print(f"  id={cab.pk:4} | {cab.convenio.nome} — {cab.nome_tabela} | {n} preço(s)")


def apagar(ids: list[int], *, confirmar: bool, empresa_id: int) -> int:
    from django.db import transaction

    from servicos_medicos.models import Cabecalho, TabelaPreco

    cabs = list(
        Cabecalho.objects.filter(pk__in=ids, empresa_id=empresa_id).select_related(
            "convenio"
        )
    )
    found_ids = {c.pk for c in cabs}
    missing = [i for i in ids if i not in found_ids]
    if missing:
        print(f"Aviso: ids não encontrados (empresa {empresa_id}): {missing}")

    total = 0
    for cab in cabs:
        n = TabelaPreco.objects.filter(cabecalho_id=cab.pk).count()
        total += n
        print(f"  id={cab.pk} | {cab.convenio.nome} — {cab.nome_tabela} | {n} preço(s)")

    print(f"Total: {total} linha(s) TabelaPreco.")
    if not confirmar:
        print("Nada apagado (use --confirmar para executar).")
        return 0

    if total == 0:
        return 0

    with transaction.atomic():
        deleted, _ = TabelaPreco.objects.filter(cabecalho_id__in=found_ids).delete()
    print(f"Apagados: {deleted} registro(s).")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Apaga preços por id de cabeçalho.")
    parser.add_argument(
        "--id",
        action="append",
        dest="ids",
        type=int,
        metavar="CABECALHO_ID",
        help="Id do cabeçalho (repita). Ex.: --id 6 --id 8",
    )
    parser.add_argument("--empresa-id", type=int, default=1)
    parser.add_argument(
        "--listar",
        action="store_true",
        help="Lista cabeçalhos e quantidade de preços",
    )
    parser.add_argument("--dry-run", action="store_true", help="Só mostra (padrão)")
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Apaga de verdade",
    )
    args = parser.parse_args()
    _setup_django()

    if args.listar:
        listar(args.empresa_id)
        return 0

    if not args.ids:
        parser.error("Informe --id 6 --id ... ou use --listar")

    confirmar = args.confirmar and not args.dry_run
    apagar(args.ids, confirmar=confirmar, empresa_id=args.empresa_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
