import os
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from empresa.models import Empresa
from faturamento_medico.services.gerar_lotes_geap import gerar_lotes_por_lote_protocolo


class Command(BaseCommand):
    help = (
        'Gera lotes internos agrupados por lote + protocolo do convênio (GEAP), '
        'cria extrato de pagamento e permite imprimir disponibilidade.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, default=16)
        parser.add_argument('--convenio', type=str, default='GEAP')
        parser.add_argument('--data-inicio', type=str, default='01/07/2026')
        parser.add_argument('--data-fim', type=str, default='31/07/2026')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not os.environ.get('DATABASE_URL'):
            url_file = Path(__file__).resolve().parents[3] / 'render_db.url'
            if url_file.is_file():
                os.environ['DATABASE_URL'] = url_file.read_text(encoding='utf-8').strip()

        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError(f'Empresa id={options["empresa_id"]} não encontrada.')

        def parse_data(raw: str):
            for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
            raise CommandError(f'Data inválida: {raw!r}')

        stats = gerar_lotes_por_lote_protocolo(
            empresa_id=empresa.id,
            convenio=options['convenio'],
            data_inicio=parse_data(options['data_inicio']),
            data_fim=parse_data(options['data_fim']),
            dry_run=options['dry_run'],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Grupos: {stats['grupos']} | Faturamentos: {stats['faturamentos']} | "
                f"Ignorados: {stats['ignorados']} | Lotes: {len(stats['lotes_criados'])}"
            )
        )
        for linha in stats['detalhes']:
            self.stdout.write(linha)
