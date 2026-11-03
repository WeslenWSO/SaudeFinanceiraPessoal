#!/usr/bin/env python
"""
Gera INSERT de TabelaPreco FUSEX (convenio/cabeçalho fixos).
Fontes:
  - scripts/importar_tabela_preco_fusex.py (TABELA_RAW — oftalmologia, RX CBHPM, etc.)
  - scripts/dados/tabela_cbhpm_referencia_conv14.tsv (RX/US/TC/RM das tabelas CBHPM FUSEX)
  - scripts/dados/servicos_tuss_fusex.tsv (códigos 8 dígitos para imagem)

  python scripts/gerar_insert_tabela_preco_fusex.py --convenio 14 --cabecalho 3
"""
from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from importar_servicos_medicos_lista import _codigos_unicos  # noqa: E402
from importar_tabela_preco_fusex import TABELA_RAW, _parse_valor  # noqa: E402

FATOR_RM_COM = Decimal("1596.30") / Decimal("856.10")
FATOR_TC_ABD_COM = Decimal("1431.80") / Decimal("691.70")
FATOR_TC_COM = Decimal("1596.30") / Decimal("856.10")  # demais TC

REF_TSV = ROOT / "dados" / "tabela_cbhpm_referencia_conv14.tsv"
FUSEX_SERVICOS = ROOT / "dados" / "servicos_tuss_fusex.tsv"
OUT_PACOTE = ROOT / "dados" / "insert_fusex_tabela_conv14_cab3.sql"


def cbhpm_to_tuss(bruto: str) -> str:
    bruto = (bruto or "").strip()
    m = re.match(r"^(\d)\.(\d{2})\.(\d{2})\.(\d{2})-(\d)$", bruto)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}{m.group(5)}"
    return re.sub(r"\D", "", bruto)[:20]


def normalizar_codigo_sql(codigo: str) -> str:
    """Código para JOIN em servicos_medicos (sem pontos CBHPM)."""
    codigo = (codigo or "").strip()
    if not codigo or codigo.startswith("SC-"):
        return codigo
    if re.match(r"^\d\.\d{2}\.\d{2}\.\d{2}-\d$", codigo):
        return cbhpm_to_tuss(codigo)
    if "." in codigo:
        m = re.match(r"^([\d.]+)-(\d+)$", codigo)
        if m:
            return re.sub(r"\.", "", m.group(1)) + "-" + m.group(2)
        return re.sub(r"\.", "", codigo)
    return codigo


def normalizar_dict_precos(
    d: dict[str, tuple[Decimal, Decimal]],
) -> dict[str, tuple[Decimal, Decimal]]:
    out: dict[str, tuple[Decimal, Decimal]] = {}
    for cod, precos in d.items():
        chave = normalizar_codigo_sql(cod)
        if chave:
            out[chave] = precos
    return out


def esc(s: str) -> str:
    return (s or "").replace("'", "''")


def norm_codigo(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")[:20]


def preco_com_tc(codigo: str, sem: Decimal) -> Decimal:
    if codigo == "41001095":
        return (sem * FATOR_TC_ABD_COM).quantize(Decimal("0.01"))
    return (sem * FATOR_TC_COM).quantize(Decimal("0.01"))


def preco_com_rm(sem: Decimal) -> Decimal:
    return (sem * FATOR_RM_COM).quantize(Decimal("0.01"))


def carregar_fusex_servicos_nomes() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in FUSEX_SERVICOS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        p = raw.split("\t")
        if len(p) < 2:
            continue
        cod = norm_codigo(p[0])
        if cod:
            out[cod] = p[1].strip()[:200]
    return out


def sql_servicos_upsert(servicos: dict[str, str]) -> str:
    vals = ",\n".join(
        f"  ('{esc(c)}', '{esc(n)}')" for c, n in sorted(servicos.items())
    )
    return f"""-- ServicosMedicos FUSEX ({len(servicos)} codigos, sem pontos)

INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico)
SELECT v.codigo, v.nome, NULL
FROM (VALUES
{vals}
) AS v(codigo, nome)
ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
"""


def carregar_fusex_servicos() -> set[str]:
    out: set[str] = set()
    for raw in FUSEX_SERVICOS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        cod = norm_codigo(raw.split("\t", 1)[0])
        if cod:
            out.add(cod)
    return out


def carregar_referencia() -> dict[str, tuple[Decimal, Decimal]]:
    """codigo -> (sem, com)."""
    out: dict[str, tuple[Decimal, Decimal]] = {}
    if not REF_TSV.is_file():
        return out
    for raw in REF_TSV.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        p = raw.split("\t")
        if len(p) < 3:
            continue
        bruto = p[0].strip()
        cod = (
            cbhpm_to_tuss(bruto)
            if re.match(r"^\d\.\d{2}\.\d{2}\.\d{2}-\d$", bruto)
            else normalizar_codigo_sql(bruto)
            if "." in bruto
            else norm_codigo(bruto)
        )
        if not cod:
            continue
        sem = Decimal(p[2].replace(",", "."))
        if len(p) >= 4 and p[3].strip():
            com = Decimal(p[3].replace(",", "."))
        elif cod.startswith("411"):
            com = preco_com_rm(sem)
        elif cod.startswith("410"):
            com = preco_com_tc(cod, sem)
        else:
            com = sem
        out[cod] = (sem, com)
    return out


def precos_tabela_raw() -> dict[str, tuple[Decimal, Decimal]]:
    pares = [(c, d) for c, d, _ in TABELA_RAW]
    codigos = _codigos_unicos(pares)
    out: dict[str, tuple[Decimal, Decimal]] = {}
    for (codigo, _desc), (bruto, _, valor_txt) in zip(codigos, TABELA_RAW, strict=True):
        v = _parse_valor(valor_txt)
        chave = normalizar_codigo_sql(
            bruto if re.match(r"^\d\.\d{2}\.\d{2}\.\d{2}-\d$", bruto or "") else codigo
        )
        if chave:
            out[chave] = (v, v)
    return out


def merge_precos(*dicts: dict[str, tuple[Decimal, Decimal]]) -> dict[str, tuple[Decimal, Decimal]]:
    merged: dict[str, tuple[Decimal, Decimal]] = {}
    for d in dicts:
        merged.update(d)
    return merged


def sql_insert(
    precos: dict[str, tuple[Decimal, Decimal]],
    *,
    empresa: int,
    convenio: int,
    cabecalho: int,
) -> str:
    linhas = []
    for cod in sorted(precos):
        sem, com = precos[cod]
        linhas.append(f"  ('{esc(cod)}', {sem}, {com})")
    if not linhas:
        return "-- (nenhum preço)\n"
    vals = ",\n".join(linhas)
    alvo = f"""(
  SELECT c.empresa_id, c.convenio_id, c.id AS cabecalho_id
  FROM servicos_medicos_cabecalho c
  WHERE c.id = {cabecalho} AND c.empresa_id = {empresa}
)"""
    return f"""-- TabelaPreco FUSEX: {len(linhas)} codigos | cabecalho_id={cabecalho} empresa_id={empresa}
-- preco_apartamento = sem contraste | preco_enfermaria = com contraste (TC/RM)
-- convenio_id vem do cabecalho (nao fixar conv. errado no INSERT).

DO $check$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM servicos_medicos_cabecalho
    WHERE id = {cabecalho} AND empresa_id = {empresa}
  ) THEN
    RAISE EXCEPTION 'Cabecalho id={cabecalho} nao existe para empresa_id={empresa}. Rode fusex_diagnostico_dbeaver.sql';
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


def escrever_pacote_dbeaver(
    path: Path,
    *,
    servicos: dict[str, str],
    precos: dict[str, tuple[Decimal, Decimal]],
    empresa: int,
    convenio: int,
    cabecalho: int,
) -> None:
    preco_sql = sql_insert(
        precos,
        empresa=empresa,
        convenio=convenio,
        cabecalho=cabecalho,
    )
    header = (
        f"-- FUSEX: servicos + TabelaPreco (tabela CBHPM imagem)\n"
        f"-- empresa_id={empresa} | convenio_id={convenio} | cabecalho_id={cabecalho}\n"
        f"-- Servicos: {len(servicos)} | Precos: {len(precos)}\n"
    )
    footer = (
        f"\n-- Conferir:\n"
        f"-- SELECT COUNT(*) FROM servicos_medicos_tabelapreco\n"
        f"--  WHERE empresa_id={empresa} AND convenio_id={convenio} AND cabecalho_id={cabecalho};\n"
    )
    path.write_text(
        header
        + "\nBEGIN;\n\n"
        + sql_servicos_upsert(servicos)
        + "\n"
        + preco_sql
        + footer
        + "\nCOMMIT;\n",
        encoding="utf-8",
    )


def escrever_sql(
    path: Path,
    merged: dict[str, tuple[Decimal, Decimal]],
    *,
    empresa: int,
    convenio: int,
    cabecalho: int,
    ref_n: int,
    raw_n: int,
    titulo_extra: str = "",
) -> None:
    body = sql_insert(
        merged,
        empresa=empresa,
        convenio=convenio,
        cabecalho=cabecalho,
    )
    header = (
        f"-- FUSEX TabelaPreco {titulo_extra}| empresa_id={empresa} "
        f"convenio_id={convenio} cabecalho_id={cabecalho}\n"
        f"-- Codigos com preco na lista: {len(merged)} ({ref_n} RX/US/TC/RM + {raw_n} clinica)\n"
        f"-- 1) Rode antes: insert_servicos_fusex_novos_conv14_cab3.sql\n"
        f"-- 2) empresa_id={empresa} deve bater com cabecalho/convênio no banco\n"
    )
    footer = (
        f"\n-- Conferir quantidade gravada:\n"
        f"-- SELECT COUNT(*) FROM servicos_medicos_tabelapreco\n"
        f"--   WHERE empresa_id={empresa} AND convenio_id={convenio} AND cabecalho_id={cabecalho};\n"
    )
    path.write_text(header + "\nBEGIN;\n\n" + body + footer + "\nCOMMIT;\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--empresa-id",
        type=int,
        default=1,
        help="empresa_id do cabeçalho/convênio no Postgres (FUSEX cab 3 / conv 14 = 1)",
    )
    ap.add_argument("--convenio", type=int, default=14)
    ap.add_argument("--cabecalho", type=int, default=3)
    ap.add_argument(
        "-o",
        type=Path,
        default=OUT_PACOTE,
        help="Pacote DBeaver (servicos + precos tabela FUSEX)",
    )
    ap.add_argument(
        "--somente-preco",
        action="store_true",
        help="So TabelaPreco (sem INSERT de servicos)",
    )
    ap.add_argument(
        "--com-clinica",
        action="store_true",
        help="Inclui also TABELA_RAW clinica (oftalmologia, etc.)",
    )
    args = ap.parse_args()

    ref = carregar_referencia()
    raw = precos_tabela_raw() if args.com_clinica else {}
    fusex_codes = carregar_fusex_servicos()
    servicos_nomes = carregar_fusex_servicos_nomes()

    ref_filtrado = {c: v for c, v in ref.items() if c in fusex_codes}
    precos_imagem = normalizar_dict_precos(ref_filtrado)
    merged = normalizar_dict_precos(merge_precos(raw, ref_filtrado))

    if args.somente_preco:
        escrever_sql(
            args.o,
            precos_imagem,
            empresa=args.empresa_id,
            convenio=args.convenio,
            cabecalho=args.cabecalho,
            ref_n=len(ref_filtrado),
            raw_n=0,
            titulo_extra="(só preços) ",
        )
        print(f"{args.o} — {len(precos_imagem)} precos")
    else:
        escrever_pacote_dbeaver(
            args.o,
            servicos=servicos_nomes,
            precos=precos_imagem,
            empresa=args.empresa_id,
            convenio=args.convenio,
            cabecalho=args.cabecalho,
        )
        print(
            f"{args.o} — {len(servicos_nomes)} servicos + {len(precos_imagem)} precos "
            f"(empresa {args.empresa_id})"
        )

    img_path = ROOT / "dados" / "insert_tabela_preco_fusex_imagem_conv14_cab3.sql"
    escrever_sql(
        img_path,
        precos_imagem,
        empresa=args.empresa_id,
        convenio=args.convenio,
        cabecalho=args.cabecalho,
        ref_n=len(ref_filtrado),
        raw_n=0,
        titulo_extra="(só RX/US/TC/RM) ",
    )


if __name__ == "__main__":
    main()
