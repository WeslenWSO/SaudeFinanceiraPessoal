#!/usr/bin/env python
"""Extrai código/descrição/preço da imagem da tabela GEAP via OCR."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image
import pytesseract

IMG = Path(
    r"C:\Users\wesle\.cursor\projects\c-Users-wesle-OneDrive-Documentos-GitHub-SaudeFinanceiraPessoal\assets"
    r"\c__Users_wesle_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images_"
    r"image-f21a045e-70fe-465a-aab3-e4b236a0c0bd.png"
)


def _parse_valor(raw: str) -> str | None:
    s = raw.strip().replace(" ", "")
    if not s:
        return None
    m = re.search(r"\d+[.,]\d{2}", s)
    if not m:
        return None
    return m.group(0).replace(".", "").replace(",", ".")


def main() -> int:
    img_path = IMG
    if not img_path.is_file():
        print(f"Imagem não encontrada: {img_path}")
        return 1

    img = Image.open(img_path)
    w, h = img.size
    # coluna de preços (lado direito)
    col_valor = img.crop((int(w * 0.78), 0, w, h))
    col_codigo = img.crop((0, 0, int(w * 0.12), h))
    col_nome = img.crop((int(w * 0.12), 0, int(w * 0.78), h))

    cfg = "--psm 6 -l por"
    txt_cod = pytesseract.image_to_string(col_codigo, config=cfg)
    txt_nome = pytesseract.image_to_string(col_nome, config=cfg)
    txt_val = pytesseract.image_to_string(col_valor, config=cfg)

    linhas_cod = [l.strip() for l in txt_cod.splitlines() if l.strip()]
    linhas_nome = [l.strip() for l in txt_nome.splitlines() if l.strip()]
    linhas_val = [l.strip() for l in txt_val.splitlines() if l.strip()]

    # códigos 8 dígitos
    codigos = []
    for l in linhas_cod:
        m = re.search(r"\b(\d{8})\b", l)
        if m:
            codigos.append(m.group(1))

    valores = []
    for l in linhas_val:
        v = _parse_valor(l)
        if v:
            valores.append(v)

    print(f"Códigos OCR: {len(codigos)} | Nomes: {len(linhas_nome)} | Valores: {len(valores)}")

    n = min(len(codigos), len(linhas_nome), len(valores))
    if n < 50:
        print("OCR insuficiente, tentando modo linha única...")
        txt = pytesseract.image_to_string(img, config="--psm 6 -l por")
        registros = []
        for linha in txt.splitlines():
            linha = linha.strip()
            m = re.match(r"^(\d{8})\s+(.+?)\s+(\d+[.,]\d{2})\s*$", linha)
            if m:
                codigo, nome, val = m.groups()
                registros.append((codigo, nome.strip(), _parse_valor(val)))
        print(f"Modo linha única: {len(registros)}")
        if len(registros) >= n:
            codigos = [r[0] for r in registros]
            linhas_nome = [r[1] for r in registros]
            valores = [r[2] for r in registros]
            n = len(registros)

    linhas_out = ["codigo\tnome\tvalor"]
    for i in range(n):
        linhas_out.append(f"{codigos[i]}\t{linhas_nome[i]}\t{valores[i]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(linhas_out) + "\n", encoding="utf-8")
    print(f"Salvo: {OUT} ({n} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
