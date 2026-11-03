#!/usr/bin/env python
"""Gera insert_*_cabecalho_7.sql a partir de scripts/dados/tabela_cab7_*.tsv"""
from __future__ import annotations

from pathlib import Path

DADOS = Path(__file__).resolve().parent / "dados"
EMP, CONV, CAB = 1, 3, 7


def esc(s: str) -> str:
    return s.replace("'", "''")


def parse_tsv(path: Path, dois_precos: bool) -> list[tuple]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        p = raw.split("\t")
        if dois_precos and len(p) >= 4:
            rows.append((p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip()))
        elif len(p) >= 3:
            rows.append((p[0].strip(), p[1].strip(), p[2].strip()))
    return rows


def sql_rm_rx_us(
    nome_arquivo: str,
    rows: list[tuple],
    *,
    dois_precos: bool,
    titulo: str,
) -> str:
    serv = ",\n".join(
        f"  ('{esc(r[0])}', '{esc(r[1])}')" for r in rows
    )
    if dois_precos:
        preco = ",\n".join(
            f"  ('{esc(r[0])}', {r[2]}, {r[3]})" for r in rows
        )
        preco_insert = f"""INSERT INTO servicos_medicos_tabelapreco
  (empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria)
SELECT {EMP}, {CONV}, {CAB}, s.id, v.sem::numeric, v.com::numeric
FROM (VALUES
{preco}
) AS v(codigo, sem, com)
JOIN servicos_medicos_servicosmedicos s ON s.codigo = v.codigo
ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id)
DO UPDATE SET preco_apartamento = EXCLUDED.preco_apartamento, preco_enfermaria = EXCLUDED.preco_enfermaria;"""
    else:
        preco = ",\n".join(
            f"  ('{esc(r[0])}', {r[2]})" for r in rows
        )
        preco_insert = f"""INSERT INTO servicos_medicos_tabelapreco
  (empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria)
SELECT {EMP}, {CONV}, {CAB}, s.id, v.valor::numeric, v.valor::numeric
FROM (VALUES
{preco}
) AS v(codigo, valor)
JOIN servicos_medicos_servicosmedicos s ON s.codigo = v.codigo
ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id)
DO UPDATE SET preco_apartamento = EXCLUDED.preco_apartamento, preco_enfermaria = EXCLUDED.preco_enfermaria;"""

    return f"""-- {len(rows)} {titulo} | convenio_id={CONV} | cabecalho_id={CAB} | empresa_id={EMP}

BEGIN;

INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico)
SELECT codigo, nome, NULL FROM (VALUES
{serv}
) AS t(codigo, nome)
ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;

{preco_insert}

COMMIT;
"""


def main() -> None:
    specs = (
        ("tabela_cab7_rm.tsv", "insert_rm_cabecalho_7.sql", True, "RM"),
        ("tabela_cab7_rx.tsv", "insert_rx_cabecalho_7.sql", False, "RX"),
        ("tabela_cab7_us.tsv", "insert_us_cabecalho_7.sql", False, "US"),
    )
    parts = []
    for tsv_name, out_name, dois, titulo in specs:
        path = DADOS / tsv_name
        rows = parse_tsv(path, dois)
        sql = sql_rm_rx_us(out_name, rows, dois_precos=dois, titulo=titulo)
        out = DADOS / out_name
        out.write_text(sql, encoding="utf-8")
        print(out_name, len(rows))
        parts.append(f"-- === {titulo} ({len(rows)}) ===\n" + sql)

    tc = DADOS / "insert_tc_cabecalho_7.sql"
    if tc.is_file():
        parts.insert(0, tc.read_text(encoding="utf-8"))
    all_path = DADOS / "insert_todos_cabecalho_7.sql"
    all_path.write_text("\n\n".join(parts), encoding="utf-8")
    print("insert_todos_cabecalho_7.sql (TC+RM+RX+US)")


if __name__ == "__main__":
    main()
