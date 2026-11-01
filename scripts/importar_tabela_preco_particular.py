#!/usr/bin/env python
"""
Cadastra serviços RX e preços na TABELA PARTICULAR (Medicinarte / empresa 1).

TSV: codigo, nome, valor

  python manage.py importar_tabela_particular
  set DATABASE_URL=postgresql://...
  python scripts/importar_tabela_preco_particular.py
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONVENIO_NOME = "PARTICULAR"
CABECALHO_NOME = "TABELA PARTICULAR"
EMPRESA_ID_DEFAULT = 1
TSV_DEFAULT = Path(__file__).resolve().parent / "dados" / "tabela_preco_particular_rx.tsv"
TSV_US = Path(__file__).resolve().parent / "dados" / "tabela_preco_particular_us.tsv"
TSV_TC = Path(__file__).resolve().parent / "dados" / "tabela_preco_particular_tc.tsv"


def _load_postal():
    postal_path = Path(__file__).resolve().parent / "importar_tabela_preco_postal.py"
    spec = importlib.util.spec_from_file_location("importar_tabela_preco_postal", postal_path)
    postal = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(postal)
    return postal


def _ensure_database_url() -> bool:
    if os.environ.get("DATABASE_URL", "").strip():
        return True
    url = ROOT / "render_db.url"
    if url.is_file():
        os.environ["DATABASE_URL"] = url.read_text(encoding="utf-8").strip()
        return bool(os.environ.get("DATABASE_URL", "").strip())
    return False


def _ensure_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()


def _conectar_com_retry() -> int:
    from django.db import connection
    from django.db.utils import OperationalError

    for tentativa in range(1, 6):
        try:
            connection.ensure_connection()
            return 0
        except OperationalError as exc:
            if tentativa >= 5:
                print(f"Falha ao conectar ao PostgreSQL: {exc}", file=sys.stderr)
                return 1
            espera = tentativa * 3
            print(f"Conexão falhou (tentativa {tentativa}/5), aguardando {espera}s…")
            time.sleep(espera)
            connection.close()
    return 1


def _resolver_servico_codigo(codigo: str, nome: str, cache: dict[str, object]):
    from servicos_medicos.models import ServicosMedicos

    if codigo in cache:
        return cache[codigo], False
    servico = ServicosMedicos.objects.filter(codigo=codigo).first()
    criado = False
    if not servico:
        servico = ServicosMedicos.objects.create(
            codigo=codigo[:20], servicos=nome[:200]
        )
        criado = True
    elif nome and servico.servicos != nome:
        servico.servicos = nome[:200]
        servico.save(update_fields=["servicos"])
    cache[codigo] = servico
    return servico, criado


def _buscar_preco_por_servico(empresa, convenio, cabecalho, servico, cache: dict[int, object]):
    from servicos_medicos.models import TabelaPreco

    if servico.pk in cache:
        return cache[servico.pk]
    preco = TabelaPreco.objects.filter(
        empresa=empresa,
        convenio=convenio,
        cabecalho=cabecalho,
        codigo_servico=servico,
    ).first()
    if preco:
        cache[servico.pk] = preco
    return preco


def importar_particular(args: argparse.Namespace, postal) -> int:
    from empresa.models import Empresa
    from servicos_medicos.models import Cabecalho, Convenio, ServicosMedicos, TabelaPreco

    empresa = Empresa.objects.filter(pk=args.empresa_id).first()
    if not empresa:
        print(f"Empresa id={args.empresa_id} não encontrada.", file=sys.stderr)
        return 1

    convenio = Convenio.objects.filter(empresa=empresa, nome__iexact=args.convenio).first()
    if not convenio:
        convenio = Convenio.objects.filter(
            empresa=empresa, nome__icontains=args.convenio
        ).first()
    if not convenio:
        convenio, _ = Convenio.objects.get_or_create(empresa=empresa, nome=args.convenio)

    cabecalho = Cabecalho.objects.filter(
        empresa=empresa, convenio=convenio, nome_tabela__iexact=args.cabecalho
    ).first()
    if not cabecalho:
        cabecalho = Cabecalho.objects.filter(
            empresa=empresa,
            convenio=convenio,
            nome_tabela__icontains="PARTICULAR",
        ).first()
    if not cabecalho:
        cabecalho = Cabecalho.objects.create(
            empresa=empresa, convenio=convenio, nome_tabela=args.cabecalho
        )

    print(f"Convênio: {convenio.nome} (id={convenio.pk})")
    print(f"Cabeçalho: {cabecalho.nome_tabela} (id={cabecalho.pk})")

    codigo_exato = getattr(args, "codigo_exato", False)
    indice_servicos = postal._indice_servicos(ServicosMedicos.objects.all())
    cache_servicos: dict[str, object] = {}
    cache_precos_tuss: dict[str, object] = {}
    cache_precos_servico: dict[int, object] = {}

    servicos_criados = criados = atualizados = pulados = 0

    dois_precos = getattr(args, "dois_precos", False)

    for linha in args.linhas:
        if dois_precos:
            chave, nome, valor_sem, valor_com = linha
        else:
            chave, nome, valor_sem = linha
            valor_com = valor_sem

        if codigo_exato or dois_precos:
            servico, servico_novo = _resolver_servico_codigo(chave, nome, cache_servicos)
        else:
            servico, servico_novo = postal._resolver_servico(
                chave, nome, indice_servicos, cache_servicos
            )
        if servico_novo:
            servicos_criados += 1

        if codigo_exato or dois_precos:
            if args.somente_novos:
                existente = _buscar_preco_por_servico(
                    empresa, convenio, cabecalho, servico, cache_precos_servico
                )
                if existente:
                    pulados += 1
                    continue
            preco = _buscar_preco_por_servico(
                empresa, convenio, cabecalho, servico, cache_precos_servico
            )
        else:
            if args.somente_novos:
                existente = postal._buscar_preco_por_tuss(
                    empresa, convenio, cabecalho, chave, cache_precos_tuss
                )
                if existente:
                    pulados += 1
                    continue
            preco = postal._buscar_preco_por_tuss(
                empresa, convenio, cabecalho, chave, cache_precos_tuss
            )

        if preco:
            mudou = False
            if (
                preco.preco_apartamento != valor_sem
                or preco.preco_enfermaria != valor_com
            ):
                preco.preco_apartamento = valor_sem
                preco.preco_enfermaria = valor_com
                mudou = True
            if (
                not codigo_exato
                and not dois_precos
                and postal.TUSS_RE.fullmatch(servico.codigo)
                and preco.codigo_servico_id != servico.pk
            ):
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
                preco_apartamento=valor_sem,
                preco_enfermaria=valor_com,
            )
            if codigo_exato or dois_precos:
                cache_precos_servico[servico.pk] = preco
            else:
                cache_precos_tuss[chave] = preco
            criados += 1

    removidos = 0
    if not codigo_exato and not dois_precos:
        removidos = postal._limpar_duplicatas_postal(empresa, convenio, cabecalho)

    total = TabelaPreco.objects.filter(
        empresa=empresa, convenio=convenio, cabecalho=cabecalho
    ).count()
    print(
        f"ServicosMedicos novos: {servicos_criados} | TabelaPreco criados: {criados} | "
        f"atualizados: {atualizados} | pulados: {pulados} | duplicatas removidas: {removidos} | "
        f"total cabeçalho: {total}"
    )
    return 0


def build_args(
    *,
    dry_run: bool = False,
    arquivo: Path | None = None,
    empresa_id: int = EMPRESA_ID_DEFAULT,
    convenio: str = CONVENIO_NOME,
    cabecalho: str = CABECALHO_NOME,
    somente_novos: bool = False,
    codigo_exato: bool = False,
    dois_precos: bool = False,
    linhas=None,
) -> argparse.Namespace:
    return argparse.Namespace(
        dry_run=dry_run,
        arquivo=arquivo or TSV_DEFAULT,
        empresa_id=empresa_id,
        convenio=convenio,
        cabecalho=cabecalho,
        somente_novos=somente_novos,
        codigo_exato=codigo_exato,
        dois_precos=dois_precos,
        linhas=linhas or [],
    )


def run_import(args: argparse.Namespace, *, skip_db_url_check: bool = False) -> int:
    postal = _load_postal()

    if not args.arquivo.is_file():
        print(f"Arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        return 1

    codigo_exato = getattr(args, "codigo_exato", False)
    dois_precos = getattr(args, "dois_precos", False)
    if dois_precos:
        linhas = postal._parse_tsv_dois_precos(args.arquivo)
        codigo_exato = True
        args.codigo_exato = True
    elif codigo_exato or postal._arquivo_requer_codigo_exato(args.arquivo):
        if not codigo_exato:
            print(
                "Detectado codigo com sufixo (ex.: 40103846-SED); "
                "usando importacao por codigo exato.",
            )
            args.codigo_exato = True
        linhas = postal._parse_tsv_codigo_exato(args.arquivo)
    else:
        linhas = postal._parse_tsv(args.arquivo)
    if not linhas:
        print("Nenhuma linha válida no TSV.", file=sys.stderr)
        return 1
    args.linhas = linhas

    modo = "sem/com contraste" if dois_precos else "preco unico"
    print(
        f"Linhas: {len(linhas)} | Empresa: {args.empresa_id} | "
        f"Convênio: {args.convenio} | Cabeçalho: {args.cabecalho} | Modo: {modo}"
    )

    if args.dry_run:
        for linha in linhas:
            if dois_precos:
                codigo, nome, sem, com = linha
                print(f"  {codigo}\t{nome[:45]}\tsem={sem}\tcom={com}")
            else:
                codigo, nome, valor = linha
                print(f"  {codigo}\t{nome[:50]}\t{valor}")
        return 0

    if not skip_db_url_check and not _ensure_database_url():
        print("Defina DATABASE_URL ou crie render_db.url na raiz do projeto.", file=sys.stderr)
        return 1

    _ensure_django()
    if _conectar_com_retry():
        return 1
    return importar_particular(args, postal)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--arquivo", type=Path, default=TSV_DEFAULT)
    parser.add_argument("--empresa-id", type=int, default=EMPRESA_ID_DEFAULT)
    parser.add_argument("--convenio", default=CONVENIO_NOME)
    parser.add_argument("--cabecalho", default=CABECALHO_NOME)
    parser.add_argument("--somente-novos", action="store_true")
    parser.add_argument(
        "--codigo-exato",
        action="store_true",
        help="1a coluna = codigo unico do servico (US, doppler, biopsias com sufixo)",
    )
    parser.add_argument(
        "--dois-precos",
        action="store_true",
        help="TSV com 4 colunas: codigo, nome, sem contraste, com contraste (TC)",
    )
    ns = parser.parse_args()
    args = build_args(
        dry_run=ns.dry_run,
        arquivo=ns.arquivo,
        empresa_id=ns.empresa_id,
        convenio=ns.convenio,
        cabecalho=ns.cabecalho,
        somente_novos=ns.somente_novos,
        codigo_exato=ns.codigo_exato,
        dois_precos=ns.dois_precos,
    )
    return run_import(args)


if __name__ == "__main__":
    raise SystemExit(main())
