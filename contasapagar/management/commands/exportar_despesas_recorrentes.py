from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contasapagar.services.relatorio_despesas_recorrentes import (
    exportar_xlsx_despesas_recorrentes,
    montar_relatorio_despesas_recorrentes,
    resolver_empresa_id,
)
from empresa.models import Empresa


class Command(BaseCommand):
    help = (
        'Exporta Excel de despesas recorrentes (últimos N meses) '
        'para uma empresa (razão social, nome fantasia ou id).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa',
            default='medicinarte',
            help='Id ou parte do nome da empresa (padrão: medicinarte)',
        )
        parser.add_argument('--meses', type=int, default=4)
        parser.add_argument(
            '--saida',
            default='',
            help='Caminho do .xlsx (padrão: exports/despesas_recorrentes_<empresa>.xlsx)',
        )

    def handle(self, *args, **options):
        empresa_id = resolver_empresa_id(options['empresa'])
        if not empresa_id:
            raise CommandError(
                f"Empresa não encontrada para «{options['empresa']}»."
            )
        emp = Empresa.objects.filter(pk=empresa_id).first()
        rotulo = (emp.razao if emp else '') or f'id={empresa_id}'

        ctx = montar_relatorio_despesas_recorrentes(
            empresa_id,
            meses=max(1, min(24, options['meses'])),
        )
        slug = ''.join(
            c if c.isalnum() else '_' for c in rotulo[:40].lower()
        ).strip('_') or str(empresa_id)
        saida = options['saida'] or str(
            Path('exports')
            / f"despesas_recorrentes_{slug}_{ctx['data_inicio']:%Y%m%d}_{ctx['data_fim']:%Y%m%d}.xlsx"
        )
        path = exportar_xlsx_despesas_recorrentes(
            ctx,
            saida,
            empresa_rotulo=rotulo,
        )
        from pathlib import Path
        import shutil

        docs = (
            Path.home() / 'OneDrive' / 'Documentos' / 'despesas_recorrentes_medicinarte.xlsx'
        )
        try:
            shutil.copy2(path, docs)
            copia_docs = str(docs.resolve())
        except OSError:
            copia_docs = ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{path} — {ctx["total_grupos"]} grupo(s), '
                f'{ctx["total_pagamentos"]} pagamento(s).'
            )
        )
        if copia_docs:
            self.stdout.write(self.style.SUCCESS(f'Cópia em: {copia_docs}'))