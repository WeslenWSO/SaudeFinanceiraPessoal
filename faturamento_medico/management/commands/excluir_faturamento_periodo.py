"""Exclui faturamentos médicos de um período (com dry-run e confirmação explícita)."""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from empresa.models import Empresa
from faturamento_medico.models import (
    DocumentoAnexado,
    ExtratoPagamentoConvenio,
    FaturamentoMedico,
    ItemServico,
    Lote,
)

CONFIRM_TOKEN = 'EXCLUIR'


class Command(BaseCommand):
    help = (
        'Exclui FaturamentoMedico no período informado (campo data). '
        'Itens e documentos anexados são removidos por CASCADE. '
        'Use --dry-run antes de --confirm EXCLUIR.'
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
            required=True,
            help='Data inicial inclusive (AAAA-MM-DD).',
        )
        parser.add_argument(
            '--data-fim',
            type=str,
            required=True,
            help='Data final inclusive (AAAA-MM-DD).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra contagens e lotes afetados sem apagar.',
        )
        parser.add_argument(
            '--confirm',
            type=str,
            help=f'Texto exato "{CONFIRM_TOKEN}" para executar a exclusão.',
        )

    def handle(self, *args, **options):
        empresa_id = options['empresa_id']
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist as exc:
            raise CommandError(f'Empresa id={empresa_id} não encontrada.') from exc

        di = date.fromisoformat(options['data_inicio'])
        df = date.fromisoformat(options['data_fim'])
        if di > df:
            di, df = df, di

        dry_run = options['dry_run']
        confirm = (options.get('confirm') or '').strip()

        if not dry_run and confirm != CONFIRM_TOKEN:
            raise CommandError(
                f'Informe --dry-run para simular ou --confirm {CONFIRM_TOKEN} para apagar.'
            )
        if dry_run and confirm == CONFIRM_TOKEN:
            raise CommandError('Use apenas --dry-run ou --confirm, não ambos.')

        qs = FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=di,
            data__lte=df,
        )
        fat_ids = list(qs.values_list('pk', flat=True))
        n_fats = len(fat_ids)

        n_itens = ItemServico.objects.filter(faturamento_id__in=fat_ids).count() if fat_ids else 0
        n_docs = DocumentoAnexado.objects.filter(faturamento_id__in=fat_ids).count() if fat_ids else 0

        lote_ids_raw = (
            qs.exclude(lote__isnull=True)
            .exclude(lote='')
            .values_list('lote', flat=True)
            .distinct()
        )
        lote_ids: list[int] = []
        for raw in lote_ids_raw:
            try:
                lote_ids.append(int(str(raw).strip()))
            except (TypeError, ValueError):
                self.stdout.write(self.style.WARNING(f'Lote ignorado (id inválido): {raw!r}'))

        lote_ids = sorted(set(lote_ids))

        self.stdout.write('=== Excluir faturamento por período ===')
        self.stdout.write(f'Empresa: {empresa.id} - {empresa.razao}')
        self.stdout.write(f'Periodo (campo data): {di.isoformat()} -> {df.isoformat()}')
        self.stdout.write(f'Faturamentos: {n_fats}')
        self.stdout.write(f'Itens de serviço: {n_itens}')
        self.stdout.write(f'Documentos anexados: {n_docs}')
        self.stdout.write(f'Lotes referenciados: {len(lote_ids)}')
        if lote_ids:
            self.stdout.write(f'  IDs: {", ".join(str(i) for i in lote_ids[:30])}')
            if len(lote_ids) > 30:
                self.stdout.write(f'  ... e mais {len(lote_ids) - 30}')

        if fat_ids:
            amostra = fat_ids[:15]
            self.stdout.write(f'Amostra de IDs faturamento: {amostra}')
            if len(fat_ids) > 15:
                self.stdout.write(f'  ... e mais {len(fat_ids) - 15}')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: nenhum registro foi apagado.'))
            return

        with transaction.atomic():
            deleted_count, deleted_detail = qs.delete()
            self.stdout.write(self.style.SUCCESS(f'Apagados: {deleted_count} objetos'))
            for model_label, qty in sorted(deleted_detail.items()):
                self.stdout.write(f'  {model_label}: {qty}')

            lotes_vazios = []
            for lote_id in lote_ids:
                try:
                    lote = Lote.objects.get(pk=lote_id, empresa_id=empresa_id)
                except Lote.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'Lote {lote_id} não encontrado; ignorado.'))
                    continue

                restantes = FaturamentoMedico.objects.filter(
                    empresa_id=empresa_id,
                    lote=str(lote_id),
                ).count()
                lote.atualizar_total()
                self.stdout.write(
                    f'Lote {lote_id}: {restantes} faturamento(s) restante(s); '
                    f'total_lote=R$ {lote.total_lote}'
                )
                if restantes == 0:
                    lotes_vazios.append(lote_id)
                    extrato = ExtratoPagamentoConvenio.objects.filter(lote_faturamento=lote).first()
                    if extrato:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  Lote {lote_id} ficou vazio, mas mantém extrato id={extrato.id} '
                                f'(não removido automaticamente).'
                            )
                        )

            if lotes_vazios:
                self.stdout.write(
                    self.style.WARNING(
                        f'Lotes sem faturamentos após exclusão: {lotes_vazios}'
                    )
                )

        self.stdout.write(self.style.SUCCESS('Exclusão concluída.'))
