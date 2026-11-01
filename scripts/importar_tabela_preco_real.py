#!/usr/bin/env python
"""
Importa preços (RX, US, etc.) para REAL CONVÊNIOS / cabeçalho TABELA - REAL (Medicinarte).

  python scripts/importar_tabela_preco_real.py
  python scripts/importar_tabela_preco_real.py --dry-run
  python scripts/importar_tabela_preco_real.py --somente rx us
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DADOS = Path(__file__).resolve().parent / "dados"

CONVENIO_NOME = "REAL CONVÊNIOS"
CABECALHO_NOME = "TABELA - REAL"
EMPRESA_ID = 1

LOTE = (
    ("rx", DADOS / "tabela_preco_particular_rx.tsv", {}),
    ("us", DADOS / "tabela_preco_particular_us.tsv", {"codigo_exato": True}),
    ("tc", DADOS / "tabela_preco_particular_tc.tsv", {"dois_precos": True}),
    ("rm", DADOS / "tabela_preco_rm.tsv", {"dois_precos": True}),
    ("mammo", DADOS / "tabela_preco_particular_mammo.tsv", {}),
    ("eg", DADOS / "tabela_preco_particular_eg.tsv", {}),
    ("ecg", DADOS / "tabela_preco_particular_ecg.tsv", {}),
)


def _load_particular():
    path = Path(__file__).resolve().parent / "importar_tabela_preco_particular.py"
    spec = importlib.util.spec_from_file_location("importar_tabela_preco_particular", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--empresa-id", type=int, default=EMPRESA_ID)
    parser.add_argument("--convenio", default=CONVENIO_NOME)
    parser.add_argument("--cabecalho", default=CABECALHO_NOME)
    parser.add_argument("--somente-novos", action="store_true")
    parser.add_argument(
        "modalidades",
        nargs="*",
        help="Filtrar: rx us tc rm mammo eg ecg (padrao: todas)",
    )
    args = parser.parse_args(argv)

    mod = _load_particular()
    filtro = {m.lower() for m in args.modalidades} if args.modalidades else None
    erros = 0

    for nome, arquivo, extras in LOTE:
        if filtro and nome not in filtro:
            continue
        if not arquivo.is_file():
            print(f"[{nome}] Arquivo ausente: {arquivo}", file=sys.stderr)
            erros += 1
            continue
        print(f"\n=== {nome.upper()} ===")
        imp = mod.build_args(
            dry_run=args.dry_run,
            arquivo=arquivo,
            empresa_id=args.empresa_id,
            convenio=args.convenio,
            cabecalho=args.cabecalho,
            somente_novos=args.somente_novos,
            codigo_exato=extras.get("codigo_exato", False),
            dois_precos=extras.get("dois_precos", False),
        )
        code = mod.run_import(imp, skip_db_url_check=True)
        if code:
            erros += 1

    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
