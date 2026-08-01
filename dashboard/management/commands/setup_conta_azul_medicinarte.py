"""Bootstrap ContaAzulConfig para Medicinarte."""

from django.core.management.base import BaseCommand, CommandError

from agendador_tarefas.seed_faturamento import NOME_FANTASIA_AGENDA_FATURAMENTO
from dashboard.conta_azul.config import gravar_client_secret, obter_ou_criar_config
from dashboard.conta_azul.oauth import gerar_state, url_autorizacao
from empresa.models import Empresa


class Command(BaseCommand):
    help = 'Cria/atualiza ContaAzulConfig da Medicinarte e exibe URL OAuth.'

    def add_arguments(self, parser):
        parser.add_argument('--client-id', required=True)
        parser.add_argument('--client-secret', required=True)
        parser.add_argument('--ambiente', choices=['DEV', 'PROD'], default='DEV')
        parser.add_argument('--redirect-uri', default='')

    def handle(self, *args, **options):
        empresa = (
            Empresa.objects.filter(nome_fantasia__icontains=NOME_FANTASIA_AGENDA_FATURAMENTO).first()
            or Empresa.objects.filter(razao__icontains='medicinarte').first()
        )
        if not empresa:
            raise CommandError('Empresa Medicinarte não encontrada.')

        cfg = obter_ou_criar_config(empresa)
        cfg.client_id = options['client_id']
        cfg.ambiente = options['ambiente']
        if options['redirect_uri']:
            cfg.redirect_uri = options['redirect_uri']
        gravar_client_secret(cfg, options['client_secret'])
        cfg.save()

        state = gerar_state()
        self.stdout.write(self.style.SUCCESS(
            f'Config criada para {empresa.razao} (id={empresa.pk}).',
        ))
        self.stdout.write('Abra no navegador (após login no sistema):')
        self.stdout.write(url_autorizacao(cfg, state=state))
