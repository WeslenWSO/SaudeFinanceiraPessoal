#!/usr/bin/env python
"""Transfere empréstimos R S NOBRE da empresa errada para empresa_id=19."""
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

from emprestimos.models import Emprestimo, ParcelaEmprestimo
from empresa.models import Empresa

EMPRESA_DESTINO = 19

# Contratos da tela (Bradesco + Daycoval) — cliente R S NOBRE
CONTRATOS = [
    "17585627",
    "17200456",  # extrato pode aparecer como 17700456
    "17700456",
    "17125123",
    "17007694",
    "16936573",
    "00A0034734",
]


def main() -> int:
    destino = Empresa.objects.filter(pk=EMPRESA_DESTINO).first()
    if not destino:
        print(f"Empresa {EMPRESA_DESTINO} não encontrada.", file=sys.stderr)
        return 1

    vistos = set()
    transferidos = []

    for num in CONTRATOS:
        qs = Emprestimo.objects.filter(numero_contrato=num, cliente__icontains="NOBRE")
        if not qs.exists():
            qs = Emprestimo.objects.filter(numero_contrato=num)
        for emp in qs:
            if emp.pk in vistos:
                continue
            if emp.empresa_id == EMPRESA_DESTINO:
                print(f"  já em {destino.razao}: {emp.numero_contrato} (id={emp.pk})")
                vistos.add(emp.pk)
                continue
            conflito = Emprestimo.objects.filter(
                empresa_id=EMPRESA_DESTINO,
                numero_contrato=emp.numero_contrato,
            ).exclude(pk=emp.pk).exists()
            if conflito:
                print(f"  CONFLITO contrato {emp.numero_contrato} já existe na empresa 19", file=sys.stderr)
                continue
            origem = emp.empresa_id
            n_parcelas = emp.parcelas.count()
            emp.empresa_id = EMPRESA_DESTINO
            emp.save(update_fields=["empresa_id"])
            vistos.add(emp.pk)
            transferidos.append(emp)
            print(
                f"  transferido id={emp.pk} contrato={emp.numero_contrato} "
                f"empresa {origem} -> {EMPRESA_DESTINO} ({n_parcelas} parcelas)"
            )

    print(f"\nEmpresa: {destino.razao}")
    print(f"Transferidos: {len(transferidos)}")
    total = Emprestimo.objects.filter(empresa_id=EMPRESA_DESTINO).count()
    parcelas = ParcelaEmprestimo.objects.filter(emprestimo__empresa_id=EMPRESA_DESTINO).count()
    print(f"Total empréstimos empresa {EMPRESA_DESTINO}: {total} ({parcelas} parcelas)")

    for e in Emprestimo.objects.filter(empresa_id=EMPRESA_DESTINO).order_by("numero_contrato"):
        banco = getattr(e.banco, "nome", None) or str(e.banco or "—")
        print(
            f"  {e.numero_contrato} | {banco} | R$ {e.valor_contrato} | "
            f"{e.parcelas.count()} parc."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
