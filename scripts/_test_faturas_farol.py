"""Testa parse dos extratos Farol mar–ago."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from OPCARTAO.fatura_pdf import detectar_banco_fatura_pdf
from OPCARTAO.sicoob_pdf import parse_fatura_sicoob_pdf

DIR = Path(r"c:\Users\wesle\OneDrive\Documentos\ALEX\farol")


def main():
    pdfs = sorted(
        p for p in DIR.glob("*.pdf")
        if any(m in p.name.upper() for m in ("MAR", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO"))
        and "BRADESCO" not in p.name.upper()
    )
    ok = 0
    for path in pdfs:
        with path.open("rb") as f:
            banco = detectar_banco_fatura_pdf(f)
        with path.open("rb") as f:
            d = parse_fatura_sicoob_pdf(f)
        itens = d.get("qtd_itens") or 0
        status = "OK" if itens > 0 and d.get("vencimento") and d.get("total_fatura") else "FAIL"
        if status == "OK":
            ok += 1
        print(
            f"{status} {path.name} | ref={d.get('referencia_mes')} "
            f"venc={d.get('vencimento')} total={d.get('total_fatura')} "
            f"itens={itens} final={d.get('cartao_final')} banco={banco}"
        )
    print(f"\n{ok}/{len(pdfs)} arquivos OK")


if __name__ == "__main__":
    main()
