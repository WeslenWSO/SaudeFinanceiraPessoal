"""Recalcula total dos itens quando percentual=0 zerou o valor (importação UNIMED antiga)."""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from faturamento_medico.models import FaturamentoMedico, ItemServico


class Command(BaseCommand):
    help = (
        'Corrige ItemServico com valor > 0 e total = 0 (percentual zerado). '
        'Define percentual=1 quando 0, recalcula total e atualiza faturamento.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--codigo-relatorio', type=str, help='Filtrar por código relatório.')
        parser.add_argument('--convenio', type=str, help='Filtrar por convênio (ex.: UNIMED).')
        parser.add_argument('--empresa-id', type=int, help='Filtrar por empresa.')
        parser.add_argument('--dry-run', action='store_true', help='Só mostra o que seria corrigido.')

    def handle(self, *args, **options):
        codigo = (options.get('codigo_relatorio') or '').strip()
        convenio = (options.get('convenio') or '').strip()
        empresa_id = options.get('empresa_id')
        dry_run = options.get('dry_run')

        itens = ItemServico.objects.select_related('faturamento').filter(
            Q(total=0) | Q(total__isnull=True),
        ).exclude(valor=0)

        if codigo:
            itens = itens.filter(faturamento__codigo_relatorio=codigo)
        if convenio:
            itens = itens.filter(faturamento__convenio__icontains=convenio)
        if empresa_id:
            itens = itens.filter(faturamento__empresa_id=empresa_id)

        total_itens = itens.count()
        if not total_itens:
            self.stdout.write(self.style.WARNING('Nenhum item a corrigir.'))
            return

        fat_ids = set()
        soma_nova = Decimal('0')
        for item in itens.iterator():
            pct = item.percentual or Decimal('1')
            if pct == 0:
                pct = Decimal('1')
            novo_total = Decimal(item.qt or 0) * Decimal(str(item.valor or 0)) * pct
            soma_nova += novo_total
            fat_ids.add(item.faturamento_id)

        self.stdout.write(
            f'Itens a corrigir: {total_itens} · Faturamentos: {len(fat_ids)} · '
            f'Novo total itens: R$ {soma_nova:.2f}'
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry-run — nada alterado.'))
            return

        with transaction.atomic():
            corrigidos = 0
            for item in itens.iterator():
                if not item.percentual:
                    item.percentual = Decimal('1')
                item.save()
                corrigidos += 1

            for fat in FaturamentoMedico.objects.filter(pk__in=fat_ids):
                fat.atualizar_total()

        self.stdout.write(self.style.SUCCESS(f'Corrigidos {corrigidos} itens e {len(fat_ids)} faturamentos.'))
