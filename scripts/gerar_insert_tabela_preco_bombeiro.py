#!/usr/bin/env python
"""
Gera pacote DBeaver: ServicosMedicos (somente novos) + TabelaPreco CORPO DE BOMBEIRO.

TSV: codigo, nome, valor_sem_contraste, valor_com_contraste
  -> preco_apartamento (sem), preco_enfermaria (com)

  python scripts/gerar_insert_tabela_preco_bombeiro.py --convenio 16 --cabecalho 10
"""
from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TSV = ROOT / "dados" / "tabela_preco_bombeiro.tsv"
OUT_DEFAULT = ROOT / "dados" / "insert_bombeiro_tabela_conv16_cab10.sql"


def norm_codigo(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")[:20]


def esc(s: str) -> str:
    return (s or "").replace("'", "''")[:200]


def parse_valor(texto: str) -> Decimal:
    s = (texto or "").strip().replace("R$", "").strip()
    if not s:
        return Decimal("0")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    return Decimal(s)


def carregar_tsv(path: Path) -> dict[str, tuple[str, Decimal, Decimal]]:
    out: dict[str, tuple[str, Decimal, Decimal]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        lower = raw.lower()
        if lower.startswith("codigo") or lower.startswith("código"):
            continue
        partes = raw.split("\t")
        if len(partes) < 2:
            continue
        cod = norm_codigo(partes[0])
        if not cod or not cod.isdigit():
            continue
        nome = partes[1].strip() or f"Servico {cod}"
        if len(partes) >= 4:
            sem = parse_valor(partes[2])
            com = parse_valor(partes[3])
        elif len(partes) == 3:
            sem = com = parse_valor(partes[2])
        else:
            continue
        out[cod] = (nome, sem, com)
    return out


def sql_servicos_novos(registros: dict[str, tuple[str, Decimal, Decimal]]) -> str:
    vals = ",\n".join(
        f"  ('{esc(c)}', '{esc(n)}')"
        for c, (n, _, _) in sorted(registros.items())
    )
    return f"""-- ServicosMedicos BOMBEIRO: apenas codigos NOVOS ({len(registros)} na lista)

INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico)
SELECT v.codigo, v.nome, NULL
FROM (VALUES
{vals}
) AS v(codigo, nome)
WHERE NOT EXISTS (
  SELECT 1 FROM servicos_medicos_servicosmedicos s WHERE s.codigo = v.codigo
);
"""


def sql_precos(
    registros: dict[str, tuple[str, Decimal, Decimal]],
    *,
    empresa: int,
    cabecalho: int,
) -> str:
    linhas = []
    for cod in sorted(registros):
        _, sem, com = registros[cod]
        linhas.append(f"  ('{esc(cod)}', {sem}, {com})")
    vals = ",\n".join(linhas)
    alvo = f"""(
  SELECT c.empresa_id, c.convenio_id, c.id AS cabecalho_id
  FROM servicos_medicos_cabecalho c
  WHERE c.id = {cabecalho} AND c.empresa_id = {empresa}
)"""
    return f"""-- TabelaPreco BOMBEIRO: {len(linhas)} codigos | cabecalho_id={cabecalho} empresa_id={empresa}
-- preco_apartamento = sem contraste | preco_enfermaria = com contraste

DO $check$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM servicos_medicos_cabecalho
    WHERE id = {cabecalho} AND empresa_id = {empresa}
  ) THEN
    RAISE EXCEPTION 'Cabecalho id={cabecalho} nao existe para empresa_id={empresa}';
  END IF;
END $check$;

INSERT INTO servicos_medicos_tabelapreco
  (empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria)
SELECT alvo.empresa_id, alvo.convenio_id, alvo.cabecalho_id, s.id, v.sem::numeric, v.com::numeric
FROM (VALUES
{vals}
) AS v(codigo, sem, com)
JOIN servicos_medicos_servicosmedicos s ON s.codigo = v.codigo
CROSS JOIN {alvo} alvo
ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id)
DO UPDATE SET
  preco_apartamento = EXCLUDED.preco_apartamento,
  preco_enfermaria = EXCLUDED.preco_enfermaria;
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--empresa-id",
        type=int,
        default=1,
        help="empresa_id no Postgres Render (Medicinarte = 1)",
    )
    ap.add_argument("--convenio", type=int, default=16)
    ap.add_argument("--cabecalho", type=int, default=10)
    ap.add_argument("-o", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()

    registros = carregar_tsv(TSV)
    if not registros:
        print("Nenhum registro no TSV bombeiro.", file=sys.stderr)
        return 1

    header = (
        f"-- CORPO DE BOMBEIRO: servicos novos + TabelaPreco\n"
        f"-- empresa_id={args.empresa_id} | convenio_id={args.convenio} (cab.) | cabecalho_id={args.cabecalho}\n"
        f"-- Fonte: {TSV.name} | codigos: {len(registros)}\n"
    )
    footer = (
        f"\n-- Conferir:\n"
        f"-- SELECT COUNT(*) FROM servicos_medicos_tabelapreco\n"
        f"--  WHERE empresa_id={args.empresa_id} AND cabecalho_id={args.cabecalho};\n"
    )
    body = (
        "BEGIN;\n\n"
        + sql_servicos_novos(registros)
        + "\n"
        + sql_precos(registros, empresa=args.empresa_id, cabecalho=args.cabecalho)
        + footer
        + "\nCOMMIT;\n"
    )
    args.o.write_text(header + "\n" + body, encoding="utf-8")
    print(f"{args.o} — {len(registros)} codigos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
