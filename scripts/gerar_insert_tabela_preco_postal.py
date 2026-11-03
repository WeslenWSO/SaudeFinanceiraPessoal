#!/usr/bin/env python
"""
Gera pacote DBeaver: ServicosMedicos (somente novos) + TabelaPreco POSTAL.

Codigo PDF CBHPM 9.99.99.99-9 -> 99999999 (8 digitos, sem pontos).

Fontes:
  - scripts/dados/tabela_preco_postal.tsv
  - scripts/dados/tabela_preco_postal_complemento.tsv

  python scripts/gerar_insert_tabela_preco_postal.py --convenio 15 --cabecalho 9
"""
from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TSV = ROOT / "dados" / "tabela_preco_postal.tsv"
TSV_COMP = ROOT / "dados" / "tabela_preco_postal_complemento.tsv"
OUT_DEFAULT = ROOT / "dados" / "insert_postal_tabela_conv15_cab9.sql"


def cbhpm_to_tuss(bruto: str) -> str:
    bruto = (bruto or "").strip()
    m = re.match(r"^(\d)\.(\d{1,2})\.(\d{1,2})\.(\d{2,3})-?(\d)?$", bruto)
    if m:
        g1, g2, g3, g4, g5 = m.groups()
        g2, g3 = g2.zfill(2), g3.zfill(2)
        g4 = re.sub(r"\D", "", g4)
        if g5:
            return f"{g1}{g2}{g3}{g4.zfill(2)}{g5}"[:8]
        if len(g4) == 3:
            return f"{g1}{g2}{g3}{g4}"[:8]
        return f"{g1}{g2}{g3}{g4.zfill(2)}"[:8]
    digits = re.sub(r"\D", "", bruto)
    return digits[:8] if digits else ""


def norm_codigo(raw: str) -> str:
    raw = (raw or "").strip()
    if re.match(r"^\d\.\d", raw):
        return cbhpm_to_tuss(raw)
    digits = re.sub(r"\D", "", raw)
    return digits[:20] if digits else ""


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


def carregar_tsv(*paths: Path) -> dict[str, tuple[str, Decimal]]:
    """codigo -> (nome, valor). Ultimo arquivo vence em duplicata."""
    out: dict[str, tuple[str, Decimal]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            lower = raw.lower()
            if lower.startswith("codigo") or lower.startswith("código"):
                continue
            partes = raw.split("\t")
            if len(partes) < 3:
                continue
            cod = norm_codigo(partes[0])
            if not cod:
                continue
            nome = partes[1].strip() or f"Servico {cod}"
            valor = parse_valor(partes[2])
            out[cod] = (nome, valor)
    return out


def sql_servicos_novos(registros: dict[str, tuple[str, Decimal]]) -> str:
    vals = ",\n".join(
        f"  ('{esc(c)}', '{esc(n)}')"
        for c, (n, _) in sorted(registros.items())
    )
    return f"""-- ServicosMedicos POSTAL: apenas codigos NOVOS ({len(registros)} na lista)

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
    registros: dict[str, tuple[str, Decimal]],
    *,
    empresa: int,
    cabecalho: int,
) -> str:
    linhas = []
    for cod in sorted(registros):
        _, valor = registros[cod]
        linhas.append(f"  ('{esc(cod)}', {valor}, {valor})")
    vals = ",\n".join(linhas)
    alvo = f"""(
  SELECT c.empresa_id, c.convenio_id, c.id AS cabecalho_id
  FROM servicos_medicos_cabecalho c
  WHERE c.id = {cabecalho} AND c.empresa_id = {empresa}
)"""
    return f"""-- TabelaPreco POSTAL: {len(linhas)} codigos | cabecalho_id={cabecalho} empresa_id={empresa}
-- preco_apartamento = preco_enfermaria = valor da tabela Postal

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
    ap.add_argument("--convenio", type=int, default=15, help="Referencia (convenio vem do cabecalho)")
    ap.add_argument("--cabecalho", type=int, default=9)
    ap.add_argument("-o", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()

    registros = carregar_tsv(TSV, TSV_COMP)
    if not registros:
        print("Nenhum registro nos TSV Postal.", file=sys.stderr)
        return 1

    header = (
        f"-- POSTAL SAUDE: servicos novos + TabelaPreco\n"
        f"-- empresa_id={args.empresa_id} | convenio_id={args.convenio} (cab.) | cabecalho_id={args.cabecalho}\n"
        f"-- Codigos: {len(registros)} | formato codigo: 8 digitos (sem pontos CBHPM)\n"
    )
    footer = (
        f"\n-- Conferir:\n"
        f"-- SELECT COUNT(*) FROM servicos_medicos_tabelapreco\n"
        f"--  WHERE empresa_id={args.empresa_id} AND cabecalho_id={args.cabecalho};\n"
        f"-- SELECT c.convenio_id FROM servicos_medicos_cabecalho c WHERE c.id={args.cabecalho};\n"
    )
    body = (
        "BEGIN;\n\n"
        + sql_servicos_novos(registros)
        + "\n"
        + sql_precos(
            registros,
            empresa=args.empresa_id,
            cabecalho=args.cabecalho,
        )
        + footer
        + "\nCOMMIT;\n"
    )
    args.o.write_text(header + "\n" + body, encoding="utf-8")
    print(f"{args.o} — {len(registros)} codigos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
