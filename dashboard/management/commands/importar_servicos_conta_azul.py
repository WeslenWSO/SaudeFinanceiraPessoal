"""Importa catálogo de serviços Conta Azul para o SF."""

from django.core.management.base import BaseCommand, CommandError

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.servicos import importar_servicos
from empresa.models import Empresa


class Command(BaseCommand):
    help = 'Importa serviços do Conta Azul para ServicoContaAzul (local).'

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError('Empresa não encontrada.')
        try:
            client = ContaAzulClient.para_empresa(empresa)
            stats = importar_servicos(empresa, client, dry_run=options['dry_run'])
        except ContaAzulAPIError as exc:
            raise CommandError(str(exc)) from exc

        if stats.get('erro'):
            raise CommandError(stats['erro'])
        self.stdout.write(
            f"Criados: {stats.get('criados', 0)} | "
            f"Atualizados: {stats.get('atualizados', 0)} | "
            f"Erros: {stats.get('erros', 0)}"
        )
