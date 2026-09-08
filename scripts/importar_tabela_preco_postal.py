#!/usr/bin/env python
"""
Cadastra serviços ausentes e importa tabela de preços Postal Saúde (Medicinarte).

TSV: codigo, nome, valor

  set DATABASE_URL=postgresql://...
  python scripts/importar_tabela_preco_postal.py
  python scripts/importar_tabela_preco_postal.py --dry-run
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

CONVENIO_NOME = "POSTAL SAÚDE"
CABECALHO_NOME = "TABELA - POSTAL"
EMPRESA_ID_DEFAULT = 16
TSV_DEFAULT = Path(__file__).resolve().parent / "dados" / "tabela_preco_postal.tsv"
TSV_COMPLEMENTO = Path(__file__).resolve().parent / "dados" / "tabela_preco_postal_complemento.tsv"

MAX_CODIGO = 20
MAX_SERVICO = 200
TUSS_RE = re.compile(r"^\d{8}$")


def _codigo_tuss(codigo: str) -> str:
    digits = re.sub(r"\D", "", codigo or "")
    if len(digits) < 8:
        return digits
    return digits[:8]


def _tuss_para_cbhpm(codigo: str) -> str | None:
    c = _codigo_tuss(codigo)
    if len(c) != 8:
        return None
    return f"{c[0]}.{c[1:3]}.{c[3:5]}.{c[5:7]}-{c[7]}"


def _parse_valor(texto: str) -> Decimal:
    s = (texto or "").strip().replace("R$", "").strip()
    if not s:
        raise ValueError("valor vazio")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    return Decimal(s)


def _parse_tsv(caminho: Path) -> list[tuple[str, str, Decimal]]:
    registros: list[tuple[str, str, Decimal]] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        lower = linha.lower()
        if lower.startswith("codigo") or lower.startswith("código"):
            continue
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        codigo = partes[0].strip()
        tuss = _codigo_tuss(codigo)
        if len(tuss) != 8:
            continue
        if len(partes) >= 3:
            nome = partes[1].strip()[:MAX_SERVICO]
            valor = _parse_valor(partes[2])
        else:
            nome = f"Servico {tuss}"
            valor = _parse_valor(partes[1])
        registros.append((tuss, nome, valor))
    return registros


def _mesclar_registros(*fontes: list[tuple[str, str, Decimal]]) -> list[tuple[str, str, Decimal]]:
    """Última fonte prevalece (complemento sobrescreve OCR)."""
    por_codigo: dict[str, tuple[str, str, Decimal]] = {}
    ordem: list[str] = []
    for fonte in fontes:
        for codigo, nome, valor in fonte:
            if codigo not in por_codigo:
                ordem.append(codigo)
            por_codigo[codigo] = (codigo, nome, valor)
    return [por_codigo[c] for c in ordem]


def _indice_servicos(servicos) -> dict[str, object]:
    """Mapeia código TUSS (8 dígitos) e CBHPM para ServicosMedicos."""
    indice: dict[str, object] = {}
    for servico in servicos:
        tuss = _codigo_tuss(servico.codigo)
        if len(tuss) == 8:
            indice.setdefault(tuss, servico)
        indice.setdefault(servico.codigo, servico)
        cbhpm = _tuss_para_cbhpm(servico.codigo)
        if cbhpm:
            indice.setdefault(cbhpm, servico)
    return indice


def _preferir_servico(candidatos: list) -> object:
    """Prefere registro com código TUSS puro (8 dígitos)."""
    for servico in candidatos:
        if TUSS_RE.fullmatch(servico.codigo or ""):
            return servico
    return candidatos[0]


def _resolver_servico(tuss: str, nome: str, indice: dict, cache: dict[str, object]):
    if tuss in cache:
        return cache[tuss], False

    candidatos = []
    for chave in (tuss, _tuss_para_cbhpm(tuss) or ""):
        if chave and chave in indice:
            candidatos.append(indice[chave])
    candidatos = list({s.pk: s for s in candidatos}.values())

    criado = False
    if candidatos:
        servico = _preferir_servico(candidatos)
    else:
        from servicos_medicos.models import ServicosMedicos

        servico = ServicosMedicos.objects.create(codigo=tuss, servicos=nome)
        indice[tuss] = servico
        cbhpm = _tuss_para_cbhpm(tuss)
        if cbhpm:
            indice[cbhpm] = servico
        criado = True

    if nome and (not servico.servicos or servico.servicos.startswith("Servico ")):
        servico.servicos = nome[:MAX_SERVICO]
        servico.save(update_fields=["servicos"])

    cache[tuss] = servico
    return servico, criado


def _buscar_preco_por_tuss(empresa, convenio, cabecalho, tuss: str, cache: dict[str, object]):
    if tuss in cache:
        return cache[tuss]
    from servicos_medicos.models import TabelaPreco

    for tp in TabelaPreco.objects.filter(
        empresa=empresa,
        convenio=convenio,
        cabecalho=cabecalho,
    ).select_related("codigo_servico"):
        if _codigo_tuss(tp.codigo_servico.codigo) == tuss:
            cache[tuss] = tp
            return tp
    return None


def _limpar_duplicatas_postal(empresa, convenio, cabecalho) -> int:
    from collections import defaultdict

    from servicos_medicos.models import ServicosMedicos, TabelaPreco

    grupos: dict[str, list] = defaultdict(list)
    for tp in TabelaPreco.objects.filter(
        empresa=empresa,
        convenio=convenio,
        cabecalho=cabecalho,
    ).select_related("codigo_servico"):
        tuss = _codigo_tuss(tp.codigo_servico.codigo)
        if len(tuss) == 8:
            grupos[tuss].append(tp)

    removidos = 0
    for tuss, itens in grupos.items():
        if len(itens) <= 1:
            keeper = itens[0]
            tuss_servico = ServicosMedicos.objects.filter(codigo=tuss).first()
            if tuss_servico and keeper.codigo_servico_id != tuss_servico.pk:
                keeper.codigo_servico = tuss_servico
                keeper.save(update_fields=["codigo_servico"])
            continue
        itens.sort(
            key=lambda tp: (
                0 if TUSS_RE.fullmatch(tp.codigo_servico.codigo or "") else 1,
                tp.pk,
            )
        )
        keeper = itens[0]
        tuss_servico = ServicosMedicos.objects.filter(codigo=tuss).first()
        if tuss_servico and keeper.codigo_servico_id != tuss_servico.pk:
            keeper.codigo_servico = tuss_servico
            keeper.save(update_fields=["codigo_servico"])
        for duplicata in itens[1:]:
            duplicata.delete()
            removidos += 1
    return removidos


def _remover_ausentes_postal(empresa, convenio, cabecalho, tuss_validos: set[str]) -> int:
    from servicos_medicos.models import TabelaPreco

    removidos = 0
    for tp in TabelaPreco.objects.filter(
        empresa=empresa,
        convenio=convenio,
        cabecalho=cabecalho,
    ).select_related("codigo_servico"):
        tuss = _codigo_tuss(tp.codigo_servico.codigo)
        if tuss not in tuss_validos:
            tp.delete()
            removidos += 1
    return removidos


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--arquivo", type=Path, default=TSV_DEFAULT)
    parser.add_argument("--empresa-id", type=int, default=EMPRESA_ID_DEFAULT)
    parser.add_argument("--complemento", type=Path, default=TSV_COMPLEMENTO)
    parser.add_argument(
        "--sem-complemento",
        action="store_true",
        help="Usa apenas o TSV principal (ex.: extraído do PDF completo)",
    )
    parser.add_argument(
        "--remover-ausentes",
        action="store_true",
        help="Remove preços do cabeçalho que não constam no TSV importado",
    )
    parser.add_argument("--somente-novos", action="store_true")
    parser.add_argument(
        "--sem-limpar-duplicatas",
        action="store_true",
        help="Não remove linhas duplicadas CBHPM/TUSS após importar",
    )
    args = parser.parse_args()

    if not args.arquivo.is_file():
        print(f"Arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        print("Execute: python scripts/gerar_tsv_postal.py", file=sys.stderr)
        return 1

    fontes = [_parse_tsv(args.arquivo)]
    if not args.sem_complemento and args.complemento.is_file():
        comp = _parse_tsv(args.complemento)
        if comp:
            fontes.append(comp)
    linhas = _mesclar_registros(*fontes)
    if not linhas:
        print("Nenhuma linha válida no TSV.", file=sys.stderr)
        return 1

    print(f"Linhas: {len(linhas)} | Empresa: {args.empresa_id} | Convênio: {CONVENIO_NOME}")

    if args.dry_run:
        for codigo, nome, valor in linhas[:10]:
            print(f"  {codigo}\t{nome[:50]}\t{valor}")
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
        alt = Convenio.objects.filter(empresa=empresa, nome__icontains="POSTAL").first()
        convenio = alt
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

    indice_servicos = _indice_servicos(ServicosMedicos.objects.all())
    cache_servicos: dict[str, object] = {}
    cache_precos: dict[str, object] = {}

    servicos_criados = criados = atualizados = pulados = 0

    for tuss, nome, valor in linhas:
        servico, servico_novo = _resolver_servico(tuss, nome, indice_servicos, cache_servicos)
        if servico_novo:
            servicos_criados += 1

        if args.somente_novos:
            existente = _buscar_preco_por_tuss(empresa, convenio, cabecalho, tuss, cache_precos)
            if existente:
                pulados += 1
                continue

        preco = _buscar_preco_por_tuss(empresa, convenio, cabecalho, tuss, cache_precos)
        if preco:
            mudou = False
            if preco.preco_apartamento != valor or preco.preco_enfermaria != valor:
                preco.preco_apartamento = valor
                preco.preco_enfermaria = valor
                mudou = True
            if TUSS_RE.fullmatch(servico.codigo) and preco.codigo_servico_id != servico.pk:
                preco.codigo_servico = servico
                mudou = True
            if mudou:
                preco.save()
                atualizados += 1
        else:
            preco = TabelaPreco.objects.create(
                empresa=empresa,
                convenio=convenio,
                cabecalho=cabecalho,
                codigo_servico=servico,
                preco_apartamento=valor,
                preco_enfermaria=valor,
            )
            cache_precos[tuss] = preco
            criados += 1

    removidos = 0
    if not args.sem_limpar_duplicatas:
        removidos = _limpar_duplicatas_postal(empresa, convenio, cabecalho)

    ausentes = 0
    if args.remover_ausentes:
        tuss_validos = {tuss for tuss, _, _ in linhas}
        ausentes = _remover_ausentes_postal(empresa, convenio, cabecalho, tuss_validos)

    total = TabelaPreco.objects.filter(
        empresa=empresa, convenio=convenio, cabecalho=cabecalho
    ).count()
    print(
        f"ServicosMedicos novos: {servicos_criados} | TabelaPreco criados: {criados} | "
        f"atualizados: {atualizados} | pulados: {pulados} | duplicatas removidas: {removidos} | "
        f"ausentes removidos: {ausentes} | total cabeçalho: {total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
