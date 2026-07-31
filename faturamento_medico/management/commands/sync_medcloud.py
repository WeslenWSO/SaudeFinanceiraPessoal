from django.core.management.base import BaseCommand

from empresa.models import Empresa
from faturamento_medico.medcloud.client import MedcloudAPIError
from faturamento_medico.medcloud.sync import sincronizar_agendas_concluidas, sincronizar_links_laudos


class Command(BaseCommand):
    help = (
        'Sincroniza agendas concluídas e/ou links de laudo MedCloud '
        'para o faturamento médico.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa-id',
            type=int,
            required=True,
            help='ID da empresa.',
        )
        parser.add_argument(
            '--data-inicio',
            type=str,
            help='Data inicial (AAAA-MM-DD). Padrão: hoje.',
        )
        parser.add_argument(
            '--data-fim',
            type=str,
            help='Data final (AAAA-MM-DD). Padrão: igual à data inicial.',
        )
        parser.add_argument(
            '--convenio',
            type=str,
            help='Filtrar por nome do convênio (opcional).',
        )
        parser.add_argument(
            '--acao',
            choices=['agendas', 'laudos', 'ambos'],
            default='ambos',
            help='O que sincronizar.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula sem gravar.',
        )

    def handle(self, *args, **options):
        from datetime import date

        empresa = Empresa.objects.get(pk=options['empresa_id'])
        hoje = date.today()
        data_inicio = options.get('data_inicio') or hoje.isoformat()
        data_fim = options.get('data_fim') or data_inicio
        di = date.fromisoformat(data_inicio)
        df = date.fromisoformat(data_fim)
        convenio = (options.get('convenio') or '').strip() or None
        acao = options['acao']
        dry = options['dry_run']

        try:
            if acao in ('agendas', 'ambos'):
                stats = sincronizar_agendas_concluidas(
                    empresa, di, df, convenio_nome=convenio, dry_run=dry,
                )
                self.stdout.write(self.style.SUCCESS(f'Agendas: {stats}'))

            if acao in ('laudos', 'ambos'):
                stats = sincronizar_links_laudos(
                    empresa, di, df, convenio_nome=convenio, dry_run=dry,
                )
                self.stdout.write(self.style.SUCCESS(f'Laudos: {stats}'))
        except MedcloudAPIError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
