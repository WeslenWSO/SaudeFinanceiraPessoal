"""Envia dados fiscais de serviços locais para o Conta Azul."""

from django.core.management.base import BaseCommand, CommandError

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.servicos import enviar_fiscal_servico, enviar_servicos_pendentes
from dashboard.models import ServicoContaAzul
from empresa.models import Empresa


class Command(BaseCommand):
    help = 'Envia cClassTrib/NBS/indicador ao Conta Azul (PATCH).'

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True)
        parser.add_argument('--pendentes', action='store_true', help='Enviar todos com fiscal_pendente_envio.')
        parser.add_argument('--servico-id', type=int, help='PK local do ServicoContaAzul.')

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError('Empresa não encontrada.')
        try:
            client = ContaAzulClient.para_empresa(empresa)
        except ContaAzulAPIError as exc:
            raise CommandError(str(exc)) from exc

        if options.get('pendentes'):
            stats = enviar_servicos_pendentes(empresa, client)
            self.stdout.write(f"Enviados: {stats['enviados']} | Erros: {stats['erros']}")
            for det in stats.get('detalhes') or []:
                self.stdout.write(self.style.WARNING(det))
            return

        pk = options.get('servico_id')
        if not pk:
            raise CommandError('Informe --pendentes ou --servico-id.')
        servico = ServicoContaAzul.objects.filter(pk=pk, empresa=empresa).first()
        if not servico:
            raise CommandError('Serviço local não encontrado.')
        try:
            resultado = enviar_fiscal_servico(empresa, client, servico)
        except ContaAzulAPIError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Enviado: {resultado.get("payload")}'))
