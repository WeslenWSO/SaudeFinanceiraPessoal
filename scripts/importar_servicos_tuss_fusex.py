#!/usr/bin/env python
"""
Cadastra ServicosMedicos TUSS (RX/US/TC/RM) — ignora código já existente.

  set DATABASE_URL=postgresql://...
  python scripts/importar_servicos_tuss_fusex.py
  python scripts/importar_servicos_tuss_fusex.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSV = Path(__file__).resolve().parent / "dados" / "servicos_tuss_fusex.tsv"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

MAX_CODIGO = 20
MAX_SERVICO = 200


def _tuss_para_cbhpm(codigo: str) -> str | None:
    """40801012 -> 4.08.01.01-2 (8 dígitos TUSS)."""
    c = re.sub(r"\D", "", codigo or "")
    if len(c) != 8:
        return None
    return f"{c[0]}.{c[1:3]}.{c[3:5]}.{c[5:7]}-{c[7]}"


def _parse_tsv(caminho: Path) -> dict[str, str]:
    encontrados: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or linha.lower().startswith("nroservico"):
            continue
        partes = linha.split("\t", 1)
        if len(partes) < 2:
            continue
        codigo = partes[0].strip()
        descricao = re.sub(r"\s+", " ", partes[1].strip())
        if codigo and descricao:
            encontrados[codigo[:MAX_CODIGO]] = descricao[:MAX_SERVICO]
    return encontrados


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--arquivo", type=Path, default=TSV)
    args = parser.parse_args()

    if not args.arquivo.is_file():
        print(f"Arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        return 1

    servicos = _parse_tsv(args.arquivo)
    print(f"Linhas na lista: {len(servicos)}")

    if args.dry_run:
        for codigo in sorted(servicos)[:10]:
            cbhpm = _tuss_para_cbhpm(codigo)
            print(f"  {codigo}\t{servicos[codigo][:50]}\tCBHPM:{cbhpm}")
        print("  ...")
        return 0

    if not os.environ.get("DATABASE_URL"):
        url = ROOT / "render_db.url"
        if url.is_file():
            os.environ["DATABASE_URL"] = url.read_text(encoding="utf-8").strip()
    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 1

    import django

    django.setup()
    from servicos_medicos.models import ServicosMedicos

    existentes = set(ServicosMedicos.objects.values_list("codigo", flat=True))
    criados = pulados_codigo = pulados_cbhpm = 0

    for codigo in sorted(servicos):
        if codigo in existentes:
            pulados_codigo += 1
            continue
        cbhpm = _tuss_para_cbhpm(codigo)
        if cbhpm and cbhpm in existentes:
            pulados_cbhpm += 1
            continue
        ServicosMedicos.objects.create(codigo=codigo, servicos=servicos[codigo])
        existentes.add(codigo)
        criados += 1

    total = ServicosMedicos.objects.count()
    print(
        f"Novos: {criados} | já existia código TUSS: {pulados_codigo} | "
        f"já existia CBHPM equivalente: {pulados_cbhpm} | total: {total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
