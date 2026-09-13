"""Corrige descrição Proc:|ImpLn: dos recebimentos importados (planilha ou regravação)."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from regrarateio.import_receita_planilha import (
    corrigir_descricoes_recebimento_por_planilha,
    regravar_descricoes_recebimento_importacao,
)


class Command(BaseCommand):
    help = (
        'Corrige descrição dos lançamentos de Recebimento importados. '
        'Com --arquivo, lê procedimento da planilha original (ex.: «Procedimento Realizado»). '
        'Sem --arquivo, regrava a partir da observação do CAR (Proc: já presente).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa', type=int, required=True, help='ID da empresa')
        parser.add_argument(
            '--arquivo',
            type=str,
            help='Caminho do .xlsx de importação (ex.: Importar Receita 01-2026.xlsx)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula sem gravar no banco.',
        )

    def handle(self, *args, **options):
        empresa_id = options['empresa']
        dry = options['dry_run']
        arquivo = (options.get('arquivo') or '').strip()

        if arquivo:
            path = Path(arquivo).expanduser()
            if not path.is_file():
                raise CommandError(f'Arquivo não encontrado: {path}')
            data = path.read_bytes()
            res = corrigir_descricoes_recebimento_por_planilha(
                empresa_id, data, dry_run=dry
            )
            self.stdout.write(
                f'Planilha: {res["linhas_planilha"]} linha(s); '
                f'CAR atualizado(s): {res["atualizados_car"]}; '
                f'LR atualizado(s): {res["atualizados_lr"]}; '
                f'sem correspondência: {res["sem_match"]}; '
                f'sem procedimento na planilha: {res["sem_proc_planilha"]}.'
            )
            if res.get('avisos_planilha'):
                for av in res['avisos_planilha'][:10]:
                    self.stdout.write(self.style.WARNING(av))
        else:
            res = regravar_descricoes_recebimento_importacao(empresa_id, dry_run=dry)
            self.stdout.write(
                f'Lançamentos de recebimento regravados: {res["atualizados_lr"]}.'
            )

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run — nada foi gravado.'))
        else:
            self.stdout.write(self.style.SUCCESS('Concluído.'))
