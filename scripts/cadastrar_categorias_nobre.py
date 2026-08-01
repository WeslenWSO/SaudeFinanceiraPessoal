#!/usr/bin/env python
"""Cadastra categorias R S NOBRE (empresa 19) em MAIÚSCULAS no PostgreSQL."""
from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = (ROOT / "render_db.url").read_text(encoding="utf-8").strip()

import django

django.setup()

from categoria.models import Categoria
from empresa.models import Empresa

EMPRESA_ID = 19

NOVAS = [
    # grupo, classificacao, nomes
    (
        "3.3.1 DESPESAS ADMINISTRATIVAS",
        "3.3.1",
        [
            "ENERGIA ELÉTRICA",
            "CAMINHÃO PIPA (MANANCIAL)",
            "ÁGUA E SANEAMENTO BRK",
            "INTERNET",
            "TELEFONE",
            "MANUTENÇÃO DE EQUIPAMENTOS",
            "LIMPEZA E HIGIENIZAÇÃO (PRODUTOS/SERVIÇOS)",
            "MARKETING E PROPAGANDA (REDES SOCIAIS/PANFLETOS)",
        ],
    ),
    (
        "3.4 IMPOSTOS DA FOLHA",
        "3.4",
        [
            "INSS",
            "FGTS",
            "IRRF (0561)",
        ],
    ),
]


def _upper(s: str) -> str:
    return (s or "").strip().upper()


def main() -> int:
    empresa = Empresa.objects.filter(pk=EMPRESA_ID).first()
    if not empresa:
        print(f"Empresa id={EMPRESA_ID} não encontrada.", file=sys.stderr)
        return 1

    criadas = 0
    existentes = 0
    for grupo, classificacao, nomes in NOVAS:
        grupo_u = _upper(grupo)
        class_u = _upper(classificacao)
        for nome in nomes:
            nome_u = _upper(nome)
            qs = Categoria.objects.filter(
                empresa_id=EMPRESA_ID,
                nome__iexact=nome_u,
                tipo="D",
            )
            if qs.exists():
                cat = qs.first()
                changed = False
                if cat.grupo != grupo_u:
                    cat.grupo = grupo_u
                    changed = True
                if cat.classificacao != class_u:
                    cat.classificacao = class_u
                    changed = True
                if cat.nome != nome_u:
                    cat.nome = nome_u
                    changed = True
                if changed:
                    cat.save()
                    print(f"  atualizada id={cat.pk}: {nome_u}")
                else:
                    print(f"  já existe id={cat.pk}: {nome_u}")
                existentes += 1
                continue
            cat = Categoria.objects.create(
                empresa=empresa,
                nome=nome_u,
                grupo=grupo_u,
                classificacao=class_u,
                tipo="D",
                sintetico="A",
                conta_azul_id="",
                bloquear_sync_conta_azul=True,
            )
            print(f"  criada id={cat.pk}: {nome_u} [{grupo_u}]")
            criadas += 1

    # Corrigir maiúsculas nas demais categorias da empresa
    for cat in Categoria.objects.filter(empresa_id=EMPRESA_ID):
        novo_nome = _upper(cat.nome)
        novo_grupo = _upper(cat.grupo) if cat.grupo else cat.grupo
        if cat.nome != novo_nome or cat.grupo != novo_grupo:
            cat.nome = novo_nome
            cat.grupo = novo_grupo
            cat.save()
            print(f"  upper id={cat.pk}: {novo_nome}")

    print(f"\nEmpresa: {empresa.razao}")
    print(f"Criadas: {criadas} | Já existiam: {existentes}")
    print(f"Total categorias empresa: {Categoria.objects.filter(empresa_id=EMPRESA_ID).count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
