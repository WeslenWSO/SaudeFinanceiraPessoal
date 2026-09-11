"""Sincroniza dados Conta Azul para uma empresa."""

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from dashboard.conta_azul.client import ContaAzulAPIError
from dashboard.conta_azul.config import obter_ou_criar_config, gravar_client_secret
from dashboard.conta_azul.sync import sincronizar_conta_azul
from empresa.models import Empresa


class Command(BaseCommand):
    help = 'Sincroniza cadastros e/ou lançamentos Conta Azul para uma empresa.'

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True)
        parser.add_argument('--cadastros', action='store_true')
        parser.add_argument('--receitas', action='store_true')
        parser.add_argument('--despesas', action='store_true')
        parser.add_argument('--transferencias', action='store_true')
        parser.add_argument('--de', dest='data_de', help='YYYY-MM-DD')
        parser.add_argument('--ate', dest='data_ate', help='YYYY-MM-DD')
        parser.add_argument(
            '--por-pagamento',
            action='store_true',
            help='Despesas: filtrar pela data de pagamento (regime de caixa).',
        )
        parser.add_argument(
            '--somente-pagos',
            action='store_true',
            help='Despesas: importar apenas títulos já pagos.',
        )
        parser.add_argument(
            '--por-mes',
            action='store_true',
            help='Executa a sync mês a mês entre --de e --ate (evita timeout).',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--client-id', help='Bootstrap client_id')
        parser.add_argument('--client-secret', help='Bootstrap client_secret')
        parser.add_argument('--ambiente', choices=['DEV', 'PROD'], default='DEV')

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError('Empresa não encontrada.')

        if options.get('client_id') and options.get('client_secret'):
            cfg = obter_ou_criar_config(empresa)
            cfg.client_id = options['client_id']
            cfg.ambiente = options['ambiente']
            gravar_client_secret(cfg, options['client_secret'])
            cfg.save()
            self.stdout.write(self.style.SUCCESS('Credenciais gravadas.'))

        hoje = date.today()
        data_de = self._parse_date(options.get('data_de')) or date(hoje.year, hoje.month, 1)
        data_ate = self._parse_date(options.get('data_ate')) or hoje

        flags = any([
            options['cadastros'],
            options['receitas'],
            options['despesas'],
            options['transferencias'],
        ])
        if not flags:
            options['cadastros'] = True

        try:
            if options['por_mes'] and data_de and data_ate:
                stats = self._sync_por_mes(empresa, options, data_de, data_ate)
            else:
                stats = sincronizar_conta_azul(
                    empresa,
                    cadastros=options['cadastros'],
                    receitas=options['receitas'],
                    despesas=options['despesas'],
                    transferencias=options['transferencias'],
                    data_de=data_de,
                    data_ate=data_ate,
                    dry_run=options['dry_run'],
                    despesas_por_pagamento=options['por_pagamento'],
                    despesas_somente_pagos=options['somente_pagos'],
                )
        except ContaAzulAPIError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(str(stats)))

    def _sync_por_mes(self, empresa, options, data_de: date, data_ate: date) -> dict:
        from calendar import monthrange

        acumulado: dict = {}
        ano, mes = data_de.year, data_de.month
        fim_ano, fim_mes = data_ate.year, data_ate.month
        while (ano, mes) <= (fim_ano, fim_mes):
            ultimo = monthrange(ano, mes)[1]
            ini = date(ano, mes, 1)
            fim = date(ano, mes, ultimo)
            if (ano, mes) == (data_de.year, data_de.month):
                ini = data_de
            if (ano, mes) == (fim_ano, fim_mes):
                fim = data_ate
            self.stdout.write(f'Sincronizando {ini.isoformat()} ate {fim.isoformat()}...')
            parcial = sincronizar_conta_azul(
                empresa,
                cadastros=options['cadastros'] and (ano, mes) == (data_de.year, data_de.month),
                receitas=options['receitas'],
                despesas=options['despesas'],
                transferencias=options['transferencias'],
                data_de=ini,
                data_ate=fim,
                dry_run=options['dry_run'],
                despesas_por_pagamento=options['por_pagamento'],
                despesas_somente_pagos=options['somente_pagos'],
            )
            for chave, val in parcial.items():
                if not isinstance(val, dict):
                    acumulado[chave] = val
                    continue
                if chave not in acumulado:
                    acumulado[chave] = dict(val)
                    continue
                dest = acumulado[chave]
                for k, v in val.items():
                    if isinstance(v, int):
                        dest[k] = dest.get(k, 0) + v
                    elif k not in dest:
                        dest[k] = v
            if mes == 12:
                ano, mes = ano + 1, 1
            else:
                mes += 1
        return acumulado

    @staticmethod
    def _parse_date(raw):
        if not raw:
            return None
        parts = raw.split('-')
        if len(parts) != 3:
            return None
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
