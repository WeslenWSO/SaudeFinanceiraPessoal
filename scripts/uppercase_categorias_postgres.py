#!/usr/bin/env python
"""Converte nome e grupo das categorias para MAIÚSCULAS no PostgreSQL."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = (ROOT / "render_db.url").read_text(encoding="utf-8").strip()

import django

django.setup()

from categoria.models import Categoria


def main() -> int:
    alteradas = 0
    for cat in Categoria.objects.all().order_by("pk"):
        novo_nome = (cat.nome or "").strip().upper()
        novo_grupo = (cat.grupo or "").strip().upper() if cat.grupo else cat.grupo
        if cat.grupo == "":
            novo_grupo = ""
        updates = {}
        if cat.nome != novo_nome:
            updates["nome"] = novo_nome
        if cat.grupo != novo_grupo:
            updates["grupo"] = novo_grupo
        if updates:
            Categoria.objects.filter(pk=cat.pk).update(**updates)
            alteradas += 1
            print(f"  id={cat.pk} empresa={cat.empresa_id}: {updates}")
    print(f"\n{alteradas} categoria(s) atualizada(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
