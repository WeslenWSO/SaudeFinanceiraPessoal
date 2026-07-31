#!/usr/bin/env python
"""Detecta linhas da tabela GEAP na imagem e extrai região de preços."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

IMG = Path(r"C:\Users\wesle\.cursor\projects\c-Users-wesle-OneDrive-Documentos-GitHub-SaudeFinanceiraPessoal\assets\c__Users_wesle_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images_image-f21a045e-70fe-465a-aab3-e4b236a0c0bd.png")
OUT_DIR = Path(__file__).resolve().parent / "dados" / "geap_rows"


def main() -> int:
    img = Image.open(IMG).convert("RGB")
    arr = np.array(img)
    h, w, _ = arr.shape
    print(f"Image: {w}x{h}")

    # média RGB por linha
    row_mean = arr.mean(axis=(1, 2))
    # detectar transições (alternância de cor de fundo)
    dif = np.abs(np.diff(row_mean))
    threshold = dif.mean() + dif.std() * 0.5
    transitions = np.where(dif > threshold)[0]

    # agrupar transições próximas
    groups: list[tuple[int, int]] = []
    if len(transitions):
        start = transitions[0]
        prev = transitions[0]
        for t in transitions[1:]:
            if t - prev > 3:
                groups.append((start, prev))
                start = t
            prev = t
        groups.append((start, prev))

    print(f"Transições: {len(transitions)} grupos: {len(groups)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # salvar recortes de cada faixa entre transições
    bounds = [0] + [g[0] for g in groups] + [h - 1]
    bounds = sorted(set(bounds))
    count = 0
    for i in range(len(bounds) - 1):
        y1, y2 = bounds[i], bounds[i + 1]
        if y2 - y1 < 8:
            continue
        row = img.crop((0, y1, w, y2))
        # preço: últimos 12% da largura
        px1 = int(w * 0.82)
        price = row.crop((px1, 0, w, y2 - y1))
        code = row.crop((0, 0, int(w * 0.14), y2 - y1))
        price.save(OUT_DIR / f"price_{count:03d}.png")
        code.save(OUT_DIR / f"code_{count:03d}.png")
        count += 1
    print(f"Saved {count} row crops to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
