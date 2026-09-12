"""Exclui títulos/lançamentos gerados pela importação de planilha de receitas."""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from contasareceber.models import ContaAReceber
from regrarateio.models import LancamentoRateio


class Command(BaseCommand):
    help = (
        'Remove contas a receber importadas via planilha (observação com Pac:) '
        'e seus lançamentos de rateio, filtrando por empresa e mês de emissão.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa', type=int, required=True, help='ID da empresa')
        parser.add_argument('--ano', type=int, required=True)
        parser.add_argument('--mes', type=int, required=True)
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra quantos registros seriam excluídos, sem apagar.',
        )

    def handle(self, *args, **options):
        empresa_id = options['empresa']
        ano = options['ano']
        mes = options['mes']
        dry = options['dry_run']

        try:
            di = date(ano, mes, 1)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if mes == 12:
            df = date(ano + 1, 1, 1)
        else:
            df = date(ano, mes + 1, 1)

        cars = ContaAReceber.objects.filter(
            empresa_id=empresa_id,
            data_emissao__gte=di,
            data_emissao__lt=df,
        ).filter(
            Q(observacao__contains='Pac:') | Q(lancamentos_rateio__origem=LancamentoRateio.ORIGEM_IMPORTACAO)
        ).distinct()

        lr_qs = LancamentoRateio.objects.filter(conta_receber__in=cars)
        n_car = cars.count()
        n_lr = lr_qs.count()
        self.stdout.write(
            f'Empresa {empresa_id} · {mes:02d}/{ano}: '
            f'{n_car} título(s) a receber, {n_lr} lançamento(s) de rateio.'
        )

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run — nada foi excluído.'))
            return

        if not n_car:
            self.stdout.write('Nenhum registro para excluir.')
            return

        with transaction.atomic():
            n_lr_del, _ = lr_qs.delete()
            n_car_del, _ = cars.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Excluídos: {n_car_del} título(s) e {n_lr_del} lançamento(s) de rateio.'
            )
        )
