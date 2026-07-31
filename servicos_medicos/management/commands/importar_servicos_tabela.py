"""Importa ServicosMedicos de TSV (NroServico, NmeServico, ...)."""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from servicos_medicos.models import ServicosMedicos

MAX_CODIGO = 20
MAX_SERVICO = 200


def _parse_porte(raw: str) -> int | None:
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        val = int(raw)
        if 0 <= val <= 6:
            return val
    except ValueError:
        pass
    return None


def _parse_tabela_geap(texto: str) -> list[tuple[str, str, int | None]]:
    """Retorna lista (codigo, nome, porte_anestesico)."""
    linhas_raw = re.sub(r'\r\n?', '\n', texto).split('\n')
    buffer = ''
    registros: list[tuple[str, str, int | None]] = []

    def _processar_linha(linha: str) -> None:
        linha = linha.strip()
        if not linha:
            return
        if linha.lower().startswith('nroservico'):
            return
        partes = linha.split('\t')
        if not partes[0].strip().isdigit():
            return
        codigo = partes[0].strip()[:MAX_CODIGO]
        nome = (partes[1].strip() if len(partes) > 1 else '')[:MAX_SERVICO]
        if not codigo or not nome:
            return
        porte = _parse_porte(partes[5]) if len(partes) > 5 else None
        registros.append((codigo, nome, porte))

    for linha in linhas_raw:
        linha = linha.strip()
        if not linha:
            continue
        if linha[0].isdigit() and '\t' in linha:
            if buffer:
                _processar_linha(buffer)
                buffer = ''
            _processar_linha(linha)
        elif buffer:
            buffer = f'{buffer} {linha}'
        elif linha[0].isdigit():
            buffer = linha
        else:
            buffer = f'{buffer} {linha}' if buffer else linha

    if buffer:
        _processar_linha(buffer)

    # dedupe por código (último vence)
    unicos: dict[str, tuple[str, str, int | None]] = {}
    for codigo, nome, porte in registros:
        unicos[codigo] = (codigo, nome, porte)
    return list(unicos.values())


class Command(BaseCommand):
    help = 'Importa códigos TUSS/CBHPM para ServicosMedicos (TSV com NroServico e NmeServico).'

    def add_arguments(self, parser):
        parser.add_argument(
            'arquivo',
            nargs='?',
            default='scripts/dados/tabela_servicos_geap.tsv',
            help='Caminho do .tsv (padrão: scripts/dados/tabela_servicos_geap.tsv)',
        )
        parser.add_argument(
            '--atualizar',
            action='store_true',
            help='Atualiza descrição/porte se o código já existir.',
        )
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        caminho = Path(options['arquivo'])
        if not caminho.is_file():
            raise CommandError(f'Arquivo não encontrado: {caminho}')

        texto = caminho.read_text(encoding='utf-8', errors='replace')
        registros = _parse_tabela_geap(texto)
        if not registros:
            raise CommandError('Nenhum serviço encontrado no arquivo.')

        self.stdout.write(f'Lidos: {len(registros)} códigos')

        if options['dry_run']:
            for codigo, nome, porte in sorted(registros)[:10]:
                self.stdout.write(f'  {codigo}\t{nome[:50]}\tporte={porte}')
            self.stdout.write('  ...')
            return

        criados = atualizados = iguais = 0
        with transaction.atomic():
            for codigo, nome, porte in registros:
                obj = ServicosMedicos.objects.filter(codigo=codigo).first()
                if obj is None:
                    ServicosMedicos.objects.create(
                        codigo=codigo,
                        servicos=nome,
                        porte_anestesico=porte,
                    )
                    criados += 1
                    continue
                if not options['atualizar']:
                    iguais += 1
                    continue
                mudou = False
                if obj.servicos != nome:
                    obj.servicos = nome
                    mudou = True
                if obj.porte_anestesico != porte:
                    obj.porte_anestesico = porte
                    mudou = True
                if mudou:
                    obj.save(update_fields=['servicos', 'porte_anestesico'])
                    atualizados += 1
                else:
                    iguais += 1

        total = ServicosMedicos.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f'Novos: {criados} | atualizados: {atualizados} | '
                f'já existiam: {iguais} | total no banco: {total}'
            )
        )
