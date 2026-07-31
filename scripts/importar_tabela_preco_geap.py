#!/usr/bin/env python
"""
Importa tabela de preços GEAP (Medicinarte) vinculada aos ServicosMedicos.

  set DATABASE_URL=postgresql://...
  python scripts/importar_tabela_preco_geap.py
  python scripts/importar_tabela_preco_geap.py --dry-run
  python scripts/importar_tabela_preco_geap.py --arquivo scripts/dados/tabela_preco_geap.tsv
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

CONVENIO_NOME = "GEAP SAÚDE - AUTOESTÃO EM SAÚDE"
CABECALHO_NOME = "TABELA - GEAP"
EMPRESA_ID_DEFAULT = 16
TSV_DEFAULT = Path(__file__).resolve().parent / "dados" / "tabela_preco_geap.tsv"


def _tuss_para_cbhpm(codigo: str) -> str | None:
    c = re.sub(r"\D", "", codigo or "")
    if len(c) != 8:
        return None
    return f"{c[0]}.{c[1:3]}.{c[3:5]}.{c[5:7]}-{c[7]}"


def _parse_valor(texto: str) -> Decimal:
    s = (texto or "").strip().replace("R$", "").strip()
    if not s:
        raise ValueError("valor vazio")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _parse_tsv(caminho: Path) -> list[tuple[str, Decimal]]:
    registros: list[tuple[str, Decimal]] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or linha.lower().startswith("codigo"):
            continue
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        codigo = partes[0].strip()
        valor_raw = partes[-1].strip()
        if not codigo.isdigit():
            continue
        registros.append((codigo, _parse_valor(valor_raw)))
    return registros


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--arquivo", type=Path, default=TSV_DEFAULT)
    parser.add_argument("--empresa-id", type=int, default=EMPRESA_ID_DEFAULT)
    parser.add_argument(
        "--somente-novos",
        action="store_true",
        help="Não atualiza preços já cadastrados neste cabeçalho.",
    )
    args = parser.parse_args()

    if not args.arquivo.is_file():
        print(f"Arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        return 1

    linhas = _parse_tsv(args.arquivo)
    print(f"Linhas: {len(linhas)} | Empresa: {args.empresa_id} | Convênio: {CONVENIO_NOME}")

    if args.dry_run:
        for codigo, valor in linhas[:5]:
            print(f"  {codigo}\t{valor}")
        print("  ...")
        return 0

    if not os.environ.get("DATABASE_URL"):
        url = ROOT / "render_db.url"
        if url.is_file():
            os.environ["DATABASE_URL"] = url.read_text(encoding="utf-8").strip()
    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 1

    import django

    django.setup()
    from empresa.models import Empresa
    from servicos_medicos.models import Cabecalho, Convenio, ServicosMedicos, TabelaPreco

    empresa = Empresa.objects.filter(pk=args.empresa_id).first()
    if not empresa:
        print(f"Empresa id={args.empresa_id} não encontrada.", file=sys.stderr)
        return 1

    convenio = Convenio.objects.filter(empresa=empresa, nome=CONVENIO_NOME).first()
    if not convenio:
        convenio, _ = Convenio.objects.get_or_create(empresa=empresa, nome=CONVENIO_NOME)

    cabecalho = Cabecalho.objects.filter(
        empresa=empresa, convenio=convenio, nome_tabela=CABECALHO_NOME
    ).first()
    if not cabecalho:
        cabecalho = Cabecalho.objects.create(
            empresa=empresa, convenio=convenio, nome_tabela=CABECALHO_NOME
        )

    print(f"Convênio: {convenio.nome} (id={convenio.pk})")
    print(f"Cabeçalho: {cabecalho.nome_tabela} (id={cabecalho.pk})")

    servicos_por_codigo = {s.codigo: s for s in ServicosMedicos.objects.all()}
    cbhpm_map = {_tuss_para_cbhpm(c): c for c in servicos_por_codigo if _tuss_para_cbhpm(c)}

    existentes: set[int] = set()
    if args.somente_novos:
        existentes = set(
            TabelaPreco.objects.filter(
                empresa=empresa, convenio=convenio, cabecalho=cabecalho
            ).values_list("codigo_servico_id", flat=True)
        )

    criados = atualizados = pulados = faltando = 0
    faltando_lista: list[str] = []

    for codigo, valor in linhas:
        servico = servicos_por_codigo.get(codigo)
        if not servico:
            cbhpm = _tuss_para_cbhpm(codigo)
            alt = cbhpm_map.get(cbhpm) if cbhpm else None
            if alt:
                servico = servicos_por_codigo[alt]
        if not servico:
            faltando += 1
            faltando_lista.append(codigo)
            continue
        if args.somente_novos and servico.pk in existentes:
            pulados += 1
            continue
        _, created = TabelaPreco.objects.update_or_create(
            empresa=empresa,
            convenio=convenio,
            cabecalho=cabecalho,
            codigo_servico=servico,
            defaults={
                "preco_apartamento": valor,
                "preco_enfermaria": valor,
            },
        )
        if created:
            criados += 1
        else:
            atualizados += 1

    total = TabelaPreco.objects.filter(
        empresa=empresa, convenio=convenio, cabecalho=cabecalho
    ).count()
    print(
        f"TabelaPreco criados: {criados} | atualizados: {atualizados} | "
        f"pulados: {pulados} | sem serviço: {faltando} | total cabeçalho: {total}"
    )
    if faltando:
        print(f"AVISO: códigos sem ServicosMedicos: {', '.join(faltando_lista[:15])}", file=sys.stderr)
    return 0 if faltando == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
