#!/usr/bin/env python
from pathlib import Path

TSV = Path(__file__).resolve().parent / "dados" / "tabela_preco_real_rx.tsv"
OUT = Path(__file__).resolve().parent / "dados" / "insert_rx_real_cabecalho_8.sql"
EMP, CONV, CAB = 1, 5, 8


def esc(s: str) -> str:
    return s.replace("'", "''")


def main() -> None:
    rows: list[tuple[str, str, str]] = []
    for raw in TSV.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        p = raw.split("\t")
        if len(p) < 3:
            continue
        rows.append((p[0].strip(), p[1].strip(), p[2].strip()))

    serv_lines = ",\n".join(
        f"  ('{esc(c)}', '{esc(n)}')" for c, n, _ in rows
    )
    preco_lines = ",\n".join(
        f"  ('{esc(c)}', {v})" for c, _, v in rows
    )
    sql = f"""-- {len(rows)} RX | convenio_id={CONV} | cabecalho_id={CAB} | empresa_id={EMP}

BEGIN;

INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico)
SELECT codigo, nome, NULL FROM (VALUES
{serv_lines}
) AS t(codigo, nome)
ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;

INSERT INTO servicos_medicos_tabelapreco
  (empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria)
SELECT {EMP}, {CONV}, {CAB}, s.id, v.valor, v.valor
FROM (VALUES
{preco_lines}
) AS v(codigo, valor)
JOIN servicos_medicos_servicosmedicos s ON s.codigo = v.codigo
ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id)
DO UPDATE SET
  preco_apartamento = EXCLUDED.preco_apartamento,
  preco_enfermaria = EXCLUDED.preco_enfermaria;

COMMIT;
"""
    OUT.write_text(sql, encoding="utf-8")
    print(len(rows), OUT)


if __name__ == "__main__":
    main()
