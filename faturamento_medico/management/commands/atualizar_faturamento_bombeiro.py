import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from empresa.models import Empresa
from faturamento_medico.services.atualizar_faturamento_convenio import (
    aplicar_atualizacoes,
    carregar_planilha,
)


class Command(BaseCommand):
    help = (
        'Atualiza faturamento médico (paciente, associado, valor) e marca CONFERIDO '
        'a partir de CSV/TSV. Só altera itens com status diferente de CONFERIDO.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--arquivo',
            type=str,
            required=True,
            help='CSV/TSV com colunas: DATA, PACIENTE, NOME ASSOCIADO, PROCEDIMENTO, MODALIDADE, VALOR',
        )
        parser.add_argument(
            '--empresa-id',
            type=int,
            default=16,
            help='ID da empresa (padrão: 16 Medicinarte).',
        )
        parser.add_argument(
            '--convenio',
            type=str,
            default='CORPO DE BOMBEIRO',
            help='Filtro parcial do nome do convênio no faturamento.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula sem gravar no banco.',
        )

    def handle(self, *args, **options):
        if not os.environ.get('DATABASE_URL'):
            url_file = Path(__file__).resolve().parents[3] / 'render_db.url'
            if url_file.is_file():
                os.environ['DATABASE_URL'] = url_file.read_text(encoding='utf-8').strip()

        caminho = Path(options['arquivo'])
        if not caminho.is_file():
            raise CommandError(f'Arquivo não encontrado: {caminho}')

        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError(f'Empresa id={options["empresa_id"]} não encontrada.')

        try:
            linhas = carregar_planilha(caminho)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not linhas:
            raise CommandError('Nenhuma linha válida no arquivo.')

        self.stdout.write(
            f'Empresa: {empresa.razao} (id={empresa.id}) | '
            f'Convênio: {options["convenio"]} | Linhas: {len(linhas)} | '
            f'{"DRY-RUN" if options["dry_run"] else "GRAVAR"}'
        )

        stats = aplicar_atualizacoes(
            linhas,
            empresa_id=empresa.id,
            convenio=options['convenio'],
            dry_run=options['dry_run'],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Atualizados: {stats['atualizados']} | "
                f"Já conferidos (sem alteração): {stats['ja_conferidos_banco']} | "
                f"Não encontrados: {stats['nao_encontrados']} | "
                f"Erros: {stats['erros']}"
            )
        )
        for linha in stats['detalhes'][:50]:
            self.stdout.write(linha)
        if len(stats['detalhes']) > 50:
            self.stdout.write(f'... +{len(stats["detalhes"]) - 50} linhas no log')
