"""Exclusão em lote de contas a receber (inclui status pago, via linha de comando)."""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from contasareceber.models import BaixaContaAReceber, ContaAReceber
from empresa.models import Empresa
from extrato.models import ExtratoMovimento
from notasfiscais.models import NotaFiscalServico

CONFIRM_TOKEN = 'EXCLUIR'
BATCH = 500


class Command(BaseCommand):
    help = (
        'Exclui contas a receber de uma empresa (opcionalmente só status pago). '
        'Use --dry-run antes de --confirm EXCLUIR.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, help='ID da empresa.')
        parser.add_argument('--empresa-nome', type=str, help='Nome fantasia ou razão (ex.: Medicinarte).')
        parser.add_argument(
            '--status',
            type=str,
            default='pago',
            help='Status a excluir (padrão: pago). Use "todos" para qualquer status.',
        )
        parser.add_argument(
            '--emissao-de',
            type=str,
            help='Data emissão inicial (YYYY-MM-DD ou DD/MM/YYYY).',
        )
        parser.add_argument(
            '--emissao-ate',
            type=str,
            help='Data emissão final (YYYY-MM-DD ou DD/MM/YYYY).',
        )
        parser.add_argument('--dry-run', action='store_true', help='Só mostra quantidade e valor total.')
        parser.add_argument(
            '--confirm',
            type=str,
            help=f'Confirma exclusão digitando {CONFIRM_TOKEN}.',
        )

    def handle(self, *args, **options):
        empresa = self._resolver_empresa(options)
        status = (options.get('status') or 'pago').strip().lower()

        qs = ContaAReceber.objects.filter(empresa_id=empresa.id)
        if status != 'todos':
            qs = qs.filter(status=status)

        emissao_de = self._parse_data(options.get('emissao_de'))
        emissao_ate = self._parse_data(options.get('emissao_ate'))
        if emissao_de:
            qs = qs.filter(data_emissao__gte=emissao_de)
        if emissao_ate:
            qs = qs.filter(data_emissao__lte=emissao_ate)

        total = qs.count()
        if not total:
            self.stdout.write(self.style.WARNING('Nenhuma conta encontrada.'))
            return

        soma = qs.aggregate(s=Sum('valor_a_receber'))['s'] or 0
        periodo = ''
        if emissao_de or emissao_ate:
            de_txt = emissao_de.strftime('%d/%m/%Y') if emissao_de else '…'
            ate_txt = emissao_ate.strftime('%d/%m/%Y') if emissao_ate else '…'
            periodo = f' · Emissão: {de_txt} a {ate_txt}'
        self.stdout.write(
            f'Empresa: {empresa.nome_fantasia or empresa.razao} (id={empresa.id}) · '
            f'Status: {status}{periodo} · Contas: {total} · Soma valor: R$ {soma:.2f}'
        )

        if options.get('dry_run'):
            self.stdout.write(self.style.WARNING('Dry-run — nada excluído.'))
            return

        if options.get('confirm') != CONFIRM_TOKEN:
            raise CommandError(f'Confirme com --confirm {CONFIRM_TOKEN} (após --dry-run).')

        excluidas = 0
        while True:
            ids = list(qs.values_list('pk', flat=True)[:BATCH])
            if not ids:
                break
            with transaction.atomic():
                nota_ids = list(
                    ContaAReceber.objects.filter(pk__in=ids)
                    .exclude(nota_id__isnull=True)
                    .values_list('nota_id', flat=True)
                )
                from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

                RelatorioRecebiveisMaquinaCartao.objects.filter(
                    conta_a_receber_id__in=ids,
                    empresa_id=empresa.id,
                ).update(conta_a_receber=None)
                ExtratoMovimento.objects.filter(conta_receber_id__in=ids).delete()
                BaixaContaAReceber.objects.filter(conta_a_receber_id__in=ids).delete()
                n, _ = ContaAReceber.objects.filter(pk__in=ids).delete()
                if nota_ids:
                    NotaFiscalServico.objects.filter(pk__in=nota_ids).update(
                        status_conciliacao='nao_conciliado',
                    )
                excluidas += n

        self.stdout.write(self.style.SUCCESS(f'Excluídas {excluidas} contas a receber.'))

    @staticmethod
    def _parse_data(valor: str | None):
        if not valor:
            return None
        texto = valor.strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise CommandError(f'Data inválida: {valor!r} (use YYYY-MM-DD ou DD/MM/YYYY)')

    def _resolver_empresa(self, options) -> Empresa:
        empresa_id = options.get('empresa_id')
        if empresa_id:
            try:
                return Empresa.objects.get(pk=empresa_id)
            except Empresa.DoesNotExist as exc:
                raise CommandError(f'Empresa id={empresa_id} não encontrada.') from exc

        nome = (options.get('empresa_nome') or '').strip()
        if not nome:
            raise CommandError('Informe --empresa-id ou --empresa-nome.')

        empresa = (
            Empresa.objects.filter(nome_fantasia__icontains=nome).first()
            or Empresa.objects.filter(razao__icontains=nome).first()
        )
        if not empresa:
            raise CommandError(f'Empresa não encontrada: {nome}')
        return empresa
