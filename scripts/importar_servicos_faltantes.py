#!/usr/bin/env python
"""
Importa ServicosMedicos faltantes a partir de arquivo TSV ou texto CBHPM.

Importa somente códigos que ainda não existem em ServicosMedicos.

  set DATABASE_URL=postgresql://...
  python scripts/importar_servicos_faltantes.py --fonte cbhpm
  python scripts/importar_servicos_faltantes.py --fonte lista.tsv
  python scripts/importar_servicos_faltantes.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

MAX_CODIGO = 20
MAX_SERVICO = 200

# Capítulo 4 CBHPM — RX (4.08) e US (4.09); ignora só cabeçalhos de grupo
PREFIXOS_CBHPM = ("4.08.", "4.09.")

def _cbhpm_txt() -> Path:
    nome = "27b133e3-9bc1-4b1d-a4a9-a64f480357f0.txt"
    candidatos = [
        ROOT / "scripts" / "dados" / "cbhpm_cap4.txt",
        Path.home()
        / ".cursor/projects/c-Users-wesle-OneDrive-Documentos-GitHub-SaudeFinanceiraPessoal/agent-tools"
        / nome,
    ]
    for caminho in candidatos:
        if caminho.is_file():
            return caminho
    return candidatos[0]

CODE_RE = re.compile(r"4\.(?:08|09)\.\d{2}\.\d{2}-\d")
LINE_START_RE = re.compile(r"^(4\.(?:08|09)\.\d{2}\.\d{2}-\d)\s+(.+)$")
TABLE_RE = re.compile(r"\|\s*(4\.(?:08|09)\.\d{2}\.\d{2}-\d)\s*\|\s*([^|]+?)\s*\|")
PORTE_SPLIT_RE = re.compile(r"\s+\d[A-C]\s")


def _limpar_descricao(texto: str) -> str:
    desc = PORTE_SPLIT_RE.split(texto.strip(), maxsplit=1)[0].strip()
    desc = re.sub(r"\s+", " ", desc)
    return desc[:MAX_SERVICO]


def _codigo_valido(codigo: str) -> bool:
    if codigo.endswith("-8") and ".00-" in codigo:
        return False
    if codigo.endswith(".99-8"):
        return False
    if not any(codigo.startswith(p) for p in PREFIXOS_CBHPM):
        return False
    return len(codigo) <= MAX_CODIGO


def _parse_cbhpm(texto: str) -> dict[str, str]:
    encontrados: dict[str, str] = {}

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue

        m = LINE_START_RE.match(linha)
        if m:
            codigo, resto = m.group(1), m.group(2)
            if _codigo_valido(codigo):
                encontrados[codigo] = _limpar_descricao(resto)
            continue

        for codigo, desc in TABLE_RE.findall(linha):
            if _codigo_valido(codigo):
                encontrados[codigo] = _limpar_descricao(desc)

    # Linhas concatenadas (PDF): vários códigos na mesma linha
    for linha in texto.splitlines():
        codigos = CODE_RE.findall(linha)
        if len(codigos) < 2:
            continue
        partes = CODE_RE.split(linha)
        for codigo, parte in zip(codigos, partes[1:], strict=False):
            if not _codigo_valido(codigo):
                continue
            desc = _limpar_descricao(parte)
            if len(desc) >= 5 and codigo not in encontrados:
                encontrados[codigo] = desc

    return encontrados


def _parse_tsv(caminho: Path) -> dict[str, str]:
    encontrados: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.lower().startswith("código") or linha.startswith("#"):
            continue
        partes = re.split(r"\t+", linha, maxsplit=1)
        if len(partes) == 1:
            partes = re.split(r"\s{2,}", linha, maxsplit=1)
        if len(partes) < 2:
            continue
        codigo = partes[0].strip()
        descricao = partes[1].strip()
        if codigo and descricao and codigo != "-":
            encontrados[codigo[:MAX_CODIGO]] = descricao[:MAX_SERVICO]
    return encontrados


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fonte",
        default="cbhpm",
        help="cbhpm ou caminho .tsv/.txt (codigo<TAB>descricao)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.fonte == "cbhpm":
        cbhpm = _cbhpm_txt()
        if not cbhpm.is_file():
            print(f"Arquivo CBHPM não encontrado: {cbhpm}", file=sys.stderr)
            return 1
        servicos = _parse_cbhpm(cbhpm.read_text(encoding="utf-8", errors="ignore"))
    else:
        caminho = Path(args.fonte)
        if not caminho.is_file():
            print(f"Arquivo não encontrado: {caminho}", file=sys.stderr)
            return 1
        servicos = _parse_tsv(caminho)

    print(f"Encontrados na fonte: {len(servicos)}")

    if args.dry_run:
        for codigo in sorted(servicos)[:15]:
            print(f"  {codigo}\t{servicos[codigo][:60]}")
        print("  ...")
        return 0

    if not os.environ.get("DATABASE_URL"):
        print("Defina DATABASE_URL.", file=sys.stderr)
        return 1

    import django

    django.setup()
    from servicos_medicos.models import ServicosMedicos

    existentes = set(ServicosMedicos.objects.values_list("codigo", flat=True))
    criados = pulados = 0

    for codigo in sorted(servicos):
        if codigo in existentes:
            pulados += 1
            continue
        ServicosMedicos.objects.create(
            codigo=codigo,
            servicos=servicos[codigo],
        )
        criados += 1

    total = ServicosMedicos.objects.count()
    print(f"Novos: {criados} | já cadastrados (ignorados): {pulados} | total no banco: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
