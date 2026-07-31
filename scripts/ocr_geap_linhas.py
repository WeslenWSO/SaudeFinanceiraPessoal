#!/usr/bin/env python
"""OCR linha a linha da tabela GEAP (imagem ampliada)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

SRC = Path("scripts/dados/geap_upscaled.png")
OUT = Path("scripts/dados/tabela_preco_geap.tsv")
TSV_SERV = Path("scripts/dados/tabela_servicos_geap.tsv")


def _parse_valor(text: str) -> str | None:
    m = re.search(r"(\d{1,3}[.,]\d{2})", text.replace(" ", ""))
    if not m:
        return None
    return m.group(1).replace(".", "").replace(",", ".")


def _detect_rows(img: Image.Image) -> list[tuple[int, int]]:
    arr = np.array(img.convert("RGB"))
    h = arr.shape[0]
    row_mean = arr.mean(axis=(1, 2))
    dif = np.abs(np.diff(row_mean))
    thr = max(dif.mean() * 0.8, 1.0)
    cuts = [0]
    for i, d in enumerate(dif):
        if d > thr:
            cuts.append(i + 1)
    cuts.append(h)
    bounds: list[tuple[int, int]] = []
    for i in range(len(cuts) - 1):
        y1, y2 = cuts[i], cuts[i + 1]
        if y2 - y1 >= 14:
            bounds.append((y1, y2))
    return bounds


def main() -> int:
    if not SRC.is_file():
        print(f"Gere antes: {SRC}")
        return 1

    img = Image.open(SRC)
    engine = RapidOCR()
    rows = _detect_rows(img)
    print(f"Faixas detectadas: {len(rows)}")

    registros: list[tuple[str, str, str]] = []
    for i, (y1, y2) in enumerate(rows):
        strip = img.crop((0, y1, img.width, y2))
        result, _ = engine(np.array(strip))
        if not result:
            continue
        texts = " ".join(t[1] for t in result)
        m_code = re.search(r"\b(\d{8})\b", texts)
        if not m_code:
            continue
        codigo = m_code.group(1)
        valor = _parse_valor(texts)
        if not valor:
            # tentar só coluna direita
            px = int(strip.width * 0.75)
            price = strip.crop((px, 0, strip.width, strip.height))
            r2, _ = engine(np.array(price))
            if r2:
                valor = _parse_valor(" ".join(t[1] for t in r2))
        if not valor:
            continue
        nome = texts.replace(codigo, "").strip()
        nome = re.sub(r"\d{1,3}[.,]\d{2}", "", nome).strip(" -|")
        registros.append((codigo, nome[:200], valor))

    # dedupe
    unicos: dict[str, tuple[str, str, str]] = {}
    for codigo, nome, valor in registros:
        unicos[codigo] = (codigo, nome, valor)

    # nomes oficiais do TSV de serviços
    nomes_ref: dict[str, str] = {}
    if TSV_SERV.is_file():
        for linha in TSV_SERV.read_text(encoding="utf-8").splitlines():
            if not linha.strip() or linha.lower().startswith("nroservico"):
                continue
            p = linha.split("\t", 1)
            if len(p) >= 2 and p[0].strip().isdigit():
                nomes_ref[p[0].strip()] = p[1].strip()[:200]

    linhas_out = ["codigo\tnome\tvalor"]
    for codigo in sorted(unicos):
        _, nome, valor = unicos[codigo]
        nome = nomes_ref.get(codigo, nome)
        linhas_out.append(f"{codigo}\t{nome}\t{valor}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(linhas_out) + "\n", encoding="utf-8")
    print(f"Extraídos: {len(unicos)} -> {OUT}")
    if len(unicos) < 100:
        print("AVISO: poucos registros — revisar OCR")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
