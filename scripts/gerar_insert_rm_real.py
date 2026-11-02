#!/usr/bin/env python
"""Gera SQL (DBeaver) para RM REAL a partir de scripts/dados/tabela_preco_rm.tsv."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
TSV = ROOT / "dados" / "tabela_preco_rm.tsv"
OUT = ROOT / "dados" / "insert_rm_real_cabecalho_8.sql"

EMPRESA_ID = 1
CONVENIO_ID = 5
CABECALHO_ID = 8


def esc(s: str) -> str:
    return s.replace("'", "''")


def main() -> None:
    lines: list[str] = [
        f"-- REAL CONVÊNIOS | cabecalho_id={CABECALHO_ID} | convenio_id={CONVENIO_ID} | empresa_id={EMPRESA_ID}",
        "-- Preços: preco_apartamento = sem contraste | preco_enfermaria = com contraste",
        "",
        "BEGIN;",
        "",
    ]
    n = 0
    for raw in TSV.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or raw.lower().startswith("codigo"):
            continue
        partes = raw.split("\t")
        if len(partes) < 4:
            continue
        codigo, nome, sem, com = (p.strip() for p in partes[:4])
        c, nom = esc(codigo), esc(nome)
        lines.append(
            f"INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) "
            f"VALUES ('{c}', '{nom}', NULL) "
            f"ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;"
        )
        lines.append(
            f"INSERT INTO servicos_medicos_tabelapreco "
            f"(empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria) "
            f"SELECT {EMPRESA_ID}, {CONVENIO_ID}, {CABECALHO_ID}, s.id, {sem}::numeric, {com}::numeric "
            f"FROM servicos_medicos_servicosmedicos s WHERE s.codigo = '{c}' "
            f"ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id) "
            f"DO UPDATE SET preco_apartamento = EXCLUDED.preco_apartamento, "
            f"preco_enfermaria = EXCLUDED.preco_enfermaria;"
        )
        lines.append("")
        n += 1

    lines.append("COMMIT;")
    lines.append(f"-- Total: {n} exames RM")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Gerado {OUT} ({n} exames)")


if __name__ == "__main__":
    main()
