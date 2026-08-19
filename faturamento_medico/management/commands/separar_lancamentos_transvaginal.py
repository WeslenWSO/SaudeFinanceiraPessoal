"""Separa exames transvaginais em lançamento próprio (sem guia e senha)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from faturamento_medico.services.transvaginal_lancamento import separar_todos_transvaginais


class Command(BaseCommand):
    help = (
        'Move itens US transvaginal para faturamento separado, sem número de guia e senha. '
        'Use --dry-run para simular.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, help='Filtra pela empresa.')
        parser.add_argument('--dry-run', action='store_true', help='Somente lista o que seria alterado.')

    def handle(self, *args, **options):
        stats = separar_todos_transvaginais(
            empresa_id=options.get('empresa_id'),
            dry_run=options['dry_run'],
        )
        self.stdout.write(f"Analisados: {stats['analisados']} | Separados: {stats['separados']}")
        for linha in stats['detalhes'][:200]:
            self.stdout.write(f'  {linha}')
        if len(stats['detalhes']) > 200:
            self.stdout.write(f'  … +{len(stats["detalhes"]) - 200}')
