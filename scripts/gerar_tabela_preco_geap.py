#!/usr/bin/env python
"""Gera scripts/dados/tabela_preco_geap.tsv a partir da lista de serviços + preços OCR."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

TSV_SERV = Path(__file__).resolve().parent / "dados" / "tabela_servicos_geap.tsv"
OUT = Path(__file__).resolve().parent / "dados" / "tabela_preco_geap.tsv"

# Preços extraídos da coluna de valores da imagem GEAP, na ordem das linhas (178)
PRECOS = [
    # pchunk 0 (linhas 1-17)
    "44,45", "62,70", "27,20", "32,70", "22,25", "41,20", "24,70", "23,30", "42,70",
    "23,21", "44,22", "42,21", "22,70", "27,60", "44,70", "22,30", "32,70",
    # pchunk 0/1 (linhas 18-30)
    "34,74", "44,90", "43,18", "33,71", "26,70", "34,74", "43,18", "37,22", "33,26",
    "31,43", "43,49", "27,25", "33,26",
    # pchunk 1 (linhas 31-46)
    "31,50", "43,49", "31,26", "33,26", "31,50", "41,65", "58,76", "33,26", "74,40",
    "46,18", "33,71", "40,73", "31,43", "43,49", "63,26", "128,87",
    # pchunk 2 (linhas 47-75)
    "52,71", "28,52", "62,64", "28,52", "42,97", "51,57", "23,76", "24,94", "39,78",
    "58,45", "87,25", "42,42", "28,52", "22,43", "52,64", "42,42", "247,74", "39,78",
    "24,94", "48,47", "24,94", "51,15", "23,76", "23,76", "42,42", "24,94", "22,42",
    "39,47", "52,52",
    # pchunk 3 (linhas 76-105)
    "247,47", "205,31", "247,47", "124,82", "247,47", "204,82", "247,47", "164,84",
    "211,81", "82,20", "56,54", "167,29", "41,20", "205,31", "215,31", "74,34",
    "167,29", "124,69", "204,82", "164,71", "247,47", "204,82", "124,71", "124,71",
    "167,29", "224,74", "201,74", "125,84", "74,11", "204,74",
    # pchunk 4 (linhas 106-131)
    "72,71", "273,81", "273,81", "309,69", "273,81", "253,32", "243,14", "228,78",
    "273,81", "253,32", "273,81", "228,78", "273,81", "443,77", "443,77", "443,77",
    "228,78", "228,78", "443,77", "443,77", "443,77", "443,77", "443,77", "443,77",
    "443,77", "443,77",
    # pchunk 5 / RM angio (linhas 132-178)
    "443,77", "443,77", "443,77", "443,77", "443,77", "443,77", "443,77", "443,77",
    "443,77", "443,77", "443,77", "443,77", "443,77", "443,77", "443,77", "443,77",
    "443,77", "443,77", "443,77", "443,77", "443,77", "443,77", "443,77", "633,77",
    "633,77", "633,77", "633,77", "633,77", "633,77", "633,77", "633,77", "633,77",
    "633,77", "633,77", "633,77", "633,77", "633,77", "633,77", "633,77", "633,77",
    "633,77", "633,77", "633,77", "633,77", "633,77", "633,77", "633,77",
]


def _parse_servicos() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for linha in TSV_SERV.read_text(encoding="utf-8").splitlines():
        if not linha.strip() or linha.lower().startswith("nroservico"):
            continue
        partes = linha.split("\t")
        if partes[0].strip().isdigit() and len(partes) >= 2:
            rows.append((partes[0].strip(), partes[1].strip()[:200]))
    return rows


def main() -> int:
    servicos = _parse_servicos()
    if len(PRECOS) < len(servicos):
        print(f"AVISO: {len(PRECOS)} preços para {len(servicos)} serviços")
    n = min(len(servicos), len(PRECOS))
    linhas = ["codigo\tnome\tvalor"]
    for i in range(n):
        codigo, nome = servicos[i]
        raw = PRECOS[i].replace(".", "").replace(",", ".")
        valor = f"{Decimal(raw):.2f}"
        linhas.append(f"{codigo}\t{nome}\t{valor}")
    OUT.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Gerado {OUT} com {n} linhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
