"""Importa relatório RIS (.xlsx) a partir de arquivo local."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from empresa.models import Empresa
from faturamento_medico.services.importar_ris_planilha import importar_ris_planilha


class Command(BaseCommand):
    help = 'Importa planilha RIS (.xlsx) para faturamento médico da empresa.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa-id',
            type=int,
            required=True,
            help='ID da empresa (Medicinarte = 16).',
        )
        parser.add_argument(
            '--arquivo',
            type=str,
            required=True,
            help='Caminho do arquivo .xlsx (modelo RIS).',
        )
        parser.add_argument(
            '--substituir-periodo',
            action='store_true',
            help='Apaga faturamentos existentes no intervalo de datas da planilha antes de importar.',
        )

    def handle(self, *args, **options):
        empresa_id = options['empresa_id']
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist as exc:
            raise CommandError(f'Empresa id={empresa_id} nao encontrada.') from exc

        arquivo = Path(options['arquivo']).expanduser().resolve()
        if not arquivo.is_file():
            raise CommandError(f'Arquivo nao encontrado: {arquivo}')

        self.stdout.write(f'Empresa: {empresa.id} - {empresa.razao}')
        self.stdout.write(f'Arquivo: {arquivo}')
        if options['substituir_periodo']:
            self.stdout.write(self.style.WARNING('Modo substituir: apagando periodo da planilha antes.'))

        try:
            stats = importar_ris_planilha(
                empresa_id,
                arquivo,
                substituir_periodo=options['substituir_periodo'],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS('Importacao concluida.'))
        for chave, valor in stats.items():
            self.stdout.write(f'  {chave}: {valor}')
