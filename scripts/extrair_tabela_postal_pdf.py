#!/usr/bin/env python
"""Extrai tabela Postal Saúde do PDF (13 páginas) para TSV e OCR bruto."""
from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DADOS = Path(__file__).resolve().parent / "dados"
PDF_DEFAULT = Path(r"C:\Users\wesle\Downloads\MEDICINARTE - 03.09.2026.PDF")
OCR_OUT = DADOS / "postal_ocr_raw.txt"
TSV_OUT = DADOS / "tabela_preco_postal.tsv"

CBHPM_LINE_RE = re.compile(r"^(\d\.\d{2}\.\d{2}\.\d{2,3})\s*$")
VALOR_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})$")
SKIP_LINE_RE = re.compile(
    r"^(PRE001|TABELA DE|Evento|Descri|Valor|Grau|Reg\.|CBO|Convênio|Conv.?nio|"
    r"CPF/CNPJ|Nome:|MEDICINARTE|22|-|\s*)$",
    re.I,
)


def _cbhpm_para_tuss(cbhpm: str) -> str:
    m = re.match(r"(\d)\.(\d{1,2})\.(\d{1,2})\.(\d{2,3})", cbhpm.strip())
    if not m:
        digits = re.sub(r"\D", "", cbhpm)
        return digits[:8].zfill(8) if digits else cbhpm
    g1, g2, g3, g4 = m.groups()
    g2 = g2.zfill(2)
    g3 = g3.zfill(2)
    g4 = re.sub(r"\D", "", g4)
    if len(g4) == 3:
        return f"{g1}{g2}{g3}{g4}"
    return f"{g1}{g2}{g3}{g4.zfill(2)}"


def _parse_valor(texto: str) -> Decimal:
    s = texto.strip().replace(".", "").replace(",", ".")
    return Decimal(s)


def _parse_pagina(texto: str) -> list[tuple[str, str, Decimal]]:
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    registros: list[tuple[str, str, Decimal]] = []
    i = 0
    while i < len(linhas):
        m = CBHPM_LINE_RE.match(linhas[i])
        if not m:
            i += 1
            continue
        cbhpm = m.group(1)
        i += 1
        desc_parts: list[str] = []
        valor: Decimal | None = None
        while i < len(linhas):
            ln = linhas[i]
            if CBHPM_LINE_RE.match(ln):
                break
            if VALOR_RE.match(ln.replace(" ", "")):
                valor = _parse_valor(ln)
                i += 1
                break
            if SKIP_LINE_RE.match(ln) or ln == "22":
                i += 1
                continue
            desc_parts.append(ln)
            i += 1
        if valor is None:
            continue
        tuss = _cbhpm_para_tuss(cbhpm)
        nome = " ".join(desc_parts).strip()[:200] or f"Servico {tuss}"
        registros.append((tuss, nome, valor))
    return registros


def extrair_pdf(pdf_path: Path, *, salvar_png: bool = True) -> list[tuple[str, str, Decimal]]:
    import fitz

    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    doc = fitz.open(str(pdf_path))
    todos: dict[str, tuple[str, str, Decimal]] = {}
    ordem: list[str] = []
    ocr_partes: list[str] = []

    for idx in range(doc.page_count):
        page = doc[idx]
        texto = page.get_text()
        ocr_partes.append(f"=== PAGE {idx + 1} ===")
        ocr_partes.append(texto.rstrip())

        if salvar_png:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            png = DADOS / f"postal_page_{idx + 1}.png"
            pix.save(str(png))

        for tuss, nome, valor in _parse_pagina(texto):
            if tuss not in todos:
                ordem.append(tuss)
            todos[tuss] = (tuss, nome, valor)

    doc.close()
    OCR_OUT.write_text("\n".join(ocr_partes) + "\n", encoding="utf-8")
    return [todos[c] for c in ordem]


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai tabela Postal Saúde do PDF")
    parser.add_argument("--pdf", type=Path, default=PDF_DEFAULT)
    parser.add_argument("--tsv", type=Path, default=TSV_OUT)
    parser.add_argument("--sem-png", action="store_true")
    args = parser.parse_args()

    try:
        registros = extrair_pdf(args.pdf, salvar_png=not args.sem_png)
    except FileNotFoundError:
        print(f"PDF não encontrado: {args.pdf}", file=sys.stderr)
        print("Informe: --pdf caminho/para/MEDICINARTE.pdf", file=sys.stderr)
        return 1

    linhas = ["codigo\tnome\tvalor"]
    for codigo, nome, valor in registros:
        linhas.append(f"{codigo}\t{nome}\t{valor}")

    args.tsv.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"PDF: {args.pdf}")
    print(f"Páginas processadas | Registros: {len(registros)}")
    print(f"OCR bruto: {OCR_OUT}")
    print(f"TSV: {args.tsv}")

    mamas = next((r for r in registros if r[0] == "40901114"), None)
    if mamas:
        print(f"US MAMAS: {mamas[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
