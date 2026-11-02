#!/usr/bin/env python
"""Gera scripts/dados/insert_rm_real_cabecalho_8.sql a partir de tabela_preco_rm.tsv."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
TSV = ROOT / "dados" / "tabela_preco_rm.tsv"
OUT = ROOT / "dados" / "insert_rm_real_cabecalho_8.sql"
CABECALHO_ID = 8


def main() -> None:
    rows: list[tuple[str, str, str, str]] = []
    for line in TSV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("codigo"):
            continue
        partes = line.split("\t")
        if len(partes) < 4:
            continue
        cod, nome, sem, com = partes[0], partes[1], partes[2], partes[3]
        rows.append((cod, nome.replace("'", "''"), sem, com))

    out: list[str] = [
        "-- REAL CONVÊNIOS / TABELA REAL — Ressonância (RM)",
        f"-- Cabeçalho id={CABECALHO_ID} (REAL CONVÊNIOS — TABELA REAL)",
        "-- preco_apartamento = sem contraste | preco_enfermaria = com contraste",
        "",
        "BEGIN;",
        "",
        f"-- DELETE FROM servicos_medicos_tabelapreco WHERE cabecalho_id = {CABECALHO_ID};",
        "",
        "-- Serviços médicos",
    ]
    for cod, nome, _sem, _com in rows:
        out.append(
            f"INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) "
            f"VALUES ('{cod}', '{nome}', NULL) "
            f"ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;"
        )

    out.extend(
        [
            "",
            "-- Preços",
            "WITH cab AS (",
            f"  SELECT id, empresa_id, convenio_id FROM servicos_medicos_cabecalho WHERE id = {CABECALHO_ID}",
            "),",
            "dados (codigo, sem, com) AS (",
            "  VALUES",
        ]
    )
    vals = [f"    ('{cod}', {sem}, {com})" for cod, _n, sem, com in rows]
    out.append(",\n".join(vals))
    out.extend(
        [
            ")",
            "INSERT INTO servicos_medicos_tabelapreco (",
            "  empresa_id, convenio_id, cabecalho_id, codigo_servico_id,",
            "  preco_apartamento, preco_enfermaria",
            ")",
            "SELECT",
            "  cab.empresa_id, cab.convenio_id, cab.id, s.id, d.sem, d.com",
            "FROM dados d",
            "JOIN servicos_medicos_servicosmedicos s ON s.codigo = d.codigo",
            "CROSS JOIN cab",
            "ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id) DO UPDATE SET",
            "  preco_apartamento = EXCLUDED.preco_apartamento,",
            "  preco_enfermaria = EXCLUDED.preco_enfermaria;",
            "",
            "COMMIT;",
        ]
    )
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(rows)} linhas -> {OUT}")


if __name__ == "__main__":
    main()
