"""Desvincula recebíveis de maquininha e exclui contas a receber em status cartão."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from contasareceber.models import BaixaContaAReceber, ContaAReceber
from empresa.models import Empresa
from extrato.models import ExtratoMovimento
from notasfiscais.models import NotaFiscalServico
from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

CONFIRM_TOKEN = 'EXCLUIR'
BATCH = 500


class Command(BaseCommand):
    help = (
        'Desconcilia recebíveis de máquina (RelatorioRecebiveisMaquinaCartao) '
        'e exclui contas a receber com status cartão. Use --dry-run antes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, help='ID da empresa.')
        parser.add_argument('--empresa-nome', type=str, help='Nome fantasia ou razão (ex.: Medicinarte).')
        parser.add_argument('--dry-run', action='store_true', help='Só mostra totais.')
        parser.add_argument('--confirm', type=str, help=f'Confirma com {CONFIRM_TOKEN}.')

    def handle(self, *args, **options):
        empresa = self._resolver_empresa(options)
        contas = ContaAReceber.objects.filter(empresa_id=empresa.id, status='cartao')
        total = contas.count()
        if not total:
            self.stdout.write(self.style.WARNING('Nenhuma conta com status cartão.'))
            return

        conta_ids = list(contas.values_list('pk', flat=True))
        rel_qs = RelatorioRecebiveisMaquinaCartao.objects.filter(
            empresa_id=empresa.id,
            conta_a_receber_id__in=conta_ids,
        )
        rel_count = rel_qs.count()
        soma = contas.aggregate(s=Sum('valor_a_receber'))['s'] or 0

        self.stdout.write(
            f'Empresa: {empresa.nome_fantasia or empresa.razao} (id={empresa.id})\n'
            f'Contas cartão: {total} · Recebíveis vinculados: {rel_count} · '
            f'Soma valor: R$ {soma:.2f}'
        )

        if options.get('dry_run'):
            self.stdout.write(self.style.WARNING('Dry-run — nada alterado.'))
            return

        if options.get('confirm') != CONFIRM_TOKEN:
            raise CommandError(f'Confirme com --confirm {CONFIRM_TOKEN} (após --dry-run).')

        with transaction.atomic():
            rel_desv = rel_qs.update(
                conciliado=False,
                identificacao_extrato='',
                conta_a_receber=None,
            )
            excluidas = 0
            while True:
                ids = list(
                    ContaAReceber.objects.filter(
                        pk__in=conta_ids,
                    ).values_list('pk', flat=True)[:BATCH]
                )
                if not ids:
                    break
                nota_ids = list(
                    ContaAReceber.objects.filter(pk__in=ids)
                    .exclude(nota_id__isnull=True)
                    .values_list('nota_id', flat=True)
                )
                ExtratoMovimento.objects.filter(conta_receber_id__in=ids).delete()
                BaixaContaAReceber.objects.filter(conta_a_receber_id__in=ids).delete()
                n, _ = ContaAReceber.objects.filter(pk__in=ids).delete()
                excluidas += n
                if nota_ids:
                    NotaFiscalServico.objects.filter(pk__in=nota_ids).update(
                        status_conciliacao='nao_conciliado',
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'Desvinculados {rel_desv} recebíveis de máquina · Excluídas {excluidas} contas cartão.'
            )
        )

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
