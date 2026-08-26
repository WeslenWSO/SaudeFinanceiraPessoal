"""Sincroniza valores de itens UNIMED já importados com a planilha Excel original."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from faturamento_medico.services.importar_unimed import sincronizar_valores_unimed_planilha


class Command(BaseCommand):
    help = (
        'Corrige qt/valor/total dos itens conforme coluna Valor (R$) da planilha UNIMED. '
        'Use quando o total do sistema divergir do demonstrativo.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, required=True, help='Caminho do .xlsx UNIMED.')
        parser.add_argument('--codigo-relatorio', type=str, required=True, help='Código relatório no sistema.')
        parser.add_argument('--empresa-id', type=int, help='Filtrar por empresa.')
        parser.add_argument('--dry-run', action='store_true', help='Só mostra diferença, não grava.')

    def handle(self, *args, **options):
        path = Path(options['arquivo'])
        if not path.is_file():
            raise CommandError(f'Arquivo não encontrado: {path}')

        codigo = (options['codigo_relatorio'] or '').strip()
        xlsx_bytes = path.read_bytes()
        corrigidos, total_plan, total_antes = sincronizar_valores_unimed_planilha(
            xlsx_bytes,
            codigo,
            empresa_id=options.get('empresa_id'),
            dry_run=options.get('dry_run'),
        )

        self.stdout.write(
            f'Planilha: R$ {total_plan:.2f} · Sistema (antes): R$ {total_antes:.2f} · '
            f'Diferença: R$ {total_antes - total_plan:.2f}'
        )
        if options.get('dry_run'):
            self.stdout.write(self.style.WARNING(f'Dry-run — {corrigidos} itens seriam ajustados.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Corrigidos {corrigidos} itens.'))
