#!/usr/bin/env python
"""
Gera INSERT de ServicosMedicos (somente códigos ainda não cadastrados).
Fonte padrão: FUSEX (scripts/dados/servicos_tuss_fusex.tsv).
Códigos CBHPM 4.08.02.01-9 -> 40802019 (só dígitos).

  python scripts/gerar_insert_servicos_cbhpm.py --convenio 14 --cabecalho 3
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FUSEX_SERVICOS = ROOT / "dados" / "servicos_tuss_fusex.tsv"
POSTAL = ROOT / "dados" / "tabela_preco_postal.tsv"
EXTRA = ROOT / "dados" / "tabela_cbhpm_extra_servicos.tsv"


def norm_codigo(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return digits[:20]


def esc(s: str) -> str:
    return (s or "").replace("'", "''")[:200]


def carregar_servicos(*, fonte: str) -> dict[str, str]:
    """codigo -> nome (primeira ocorrência vence)."""
    out: dict[str, str] = {}

    def ingest(path: Path) -> None:
        if not path.is_file():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            lower = raw.lower()
            if lower.startswith("codigo") or lower.startswith("nroservico"):
                continue
            partes = raw.split("\t")
            if len(partes) < 2:
                continue
            cod = norm_codigo(partes[0])
            if not cod:
                continue
            nome = partes[1].strip()
            if cod not in out:
                out[cod] = nome

    if fonte == "fusex":
        ingest(FUSEX_SERVICOS)
        ingest(EXTRA)
        return out

    ingest(POSTAL)
    ingest(EXTRA)
    filtrado = {}
    for cod, nome in out.items():
        if cod.startswith(("408", "409", "410", "411")):
            filtrado[cod] = nome
    return filtrado


def sql_servicos_novos(servicos: dict[str, str]) -> str:
    vals = ",\n".join(
        f"  ('{esc(c)}', '{esc(n)}')" for c, n in sorted(servicos.items())
    )
    return f"""-- ServicosMedicos: apenas codigos NOVOS ({len(servicos)} linhas na lista; existentes sao ignorados)

INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico)
SELECT v.codigo, v.nome, NULL
FROM (VALUES
{vals}
) AS v(codigo, nome)
WHERE NOT EXISTS (
  SELECT 1 FROM servicos_medicos_servicosmedicos s WHERE s.codigo = v.codigo
);
"""


def carregar_precos_referencia() -> dict[str, tuple[str, str]]:
    """codigo -> (sem, com) ou (valor, valor) from extra file with 3 or 4 cols."""
    path = ROOT / "dados" / "tabela_cbhpm_referencia_conv14.tsv"
    out: dict[str, tuple[str, str]] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        p = raw.split("\t")
        cod = norm_codigo(p[0])
        if not cod:
            continue
        if len(p) >= 4:
            out[cod] = (p[2].strip(), p[3].strip())
        elif len(p) >= 3:
            out[cod] = (p[2].strip(), p[2].strip())
    return out


def sql_precos_novos(
    servicos: dict[str, str],
    precos: dict[str, tuple[str, str]],
    *,
    empresa: int,
    convenio: int,
    cabecalho: int,
) -> str:
    linhas = []
    for cod in sorted(servicos):
        if cod not in precos:
            continue
        sem, com = precos[cod]
        linhas.append(f"  ('{esc(cod)}', {sem}, {com})")
    if not linhas:
        return "-- (sem arquivo tabela_cbhpm_referencia_conv14.tsv para precos)\n"
    vals = ",\n".join(linhas)
    return f"""-- TabelaPreco: cabecalho={cabecalho} convenio={convenio} — so linhas novas

INSERT INTO servicos_medicos_tabelapreco
  (empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria)
SELECT {empresa}, {convenio}, {cabecalho}, s.id, v.sem::numeric, v.com::numeric
FROM (VALUES
{vals}
) AS v(codigo, sem, com)
JOIN servicos_medicos_servicosmedicos s ON s.codigo = v.codigo
WHERE NOT EXISTS (
  SELECT 1 FROM servicos_medicos_tabelapreco tp
  WHERE tp.empresa_id = {empresa}
    AND tp.convenio_id = {convenio}
    AND tp.cabecalho_id = {cabecalho}
    AND tp.codigo_servico_id = s.id
);
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--empresa-id", type=int, default=1)
    ap.add_argument("--convenio", type=int, default=14)
    ap.add_argument("--cabecalho", type=int, default=3)
    ap.add_argument(
        "--fonte",
        choices=("fusex", "postal"),
        default="fusex",
        help="Lista de serviços (padrão: FUSEX)",
    )
    ap.add_argument("--com-precos", action="store_true")
    ap.add_argument(
        "-o",
        type=Path,
        default=None,
        help="Saída .sql (padrão: insert_servicos_fusex_novos_conv14_cab3.sql)",
    )
    args = ap.parse_args()
    if args.o is None:
        nome = (
            "insert_servicos_fusex_novos_conv14_cab3.sql"
            if args.fonte == "fusex"
            else "insert_servicos_novos_conv14_cab3.sql"
        )
        args.o = ROOT / "dados" / nome

    servicos = carregar_servicos(fonte=args.fonte)
    parts = [
        f"-- {args.fonte.upper()} RX/US/TC/RM | convenio_id={args.convenio} | cabecalho_id={args.cabecalho}",
        "BEGIN;",
        sql_servicos_novos(servicos),
    ]
    if args.com_precos:
        precos = carregar_precos_referencia()
        parts.append(
            sql_precos_novos(
                servicos,
                precos,
                empresa=args.empresa_id,
                convenio=args.convenio,
                cabecalho=args.cabecalho,
            )
        )
    parts.append("COMMIT;")
    args.o.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"{args.o} — {len(servicos)} codigos (INSERT so nao cadastrados)")


if __name__ == "__main__":
    main()
