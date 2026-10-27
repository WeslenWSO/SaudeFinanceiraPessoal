"""Diagnóstico rápido: migrations do acerto de caixa (Render Shell)."""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection


class Command(BaseCommand):
    help = 'Verifica colunas/tabelas do acerto de caixa e migrations pendentes.'

    def handle(self, *args, **options):
        self.stdout.write('--- migrate --plan (trecho) ---')
        call_command('migrate', '--plan', verbosity=1)

        tabelas = (
            'faturamento_medico_acertocaixafechamento',
            'faturamento_medico_faturamentomedico',
        )
        with connection.cursor() as cur:
            for tabela in tabelas:
                self.stdout.write(f'\n--- colunas {tabela} (amostra) ---')
                try:
                    desc = connection.introspection.get_table_description(cur, tabela)
                    cols = [c.name for c in desc]
                    for nome in (
                        'marcado_acerto_caixa',
                        'caixa_acerto',
                        'pagamentos_acerto_json',
                    ):
                        ok = nome in cols
                        self.stdout.write(f'  {nome}: {"OK" if ok else "AUSENTE"}')
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f'  tabela indisponível: {exc}'))

            self.stdout.write('\n--- extrato.contabancaria.inativo_acerto_caixa ---')
            try:
                desc = connection.introspection.get_table_description(cur, 'extrato_contabancaria')
                cols = [c.name for c in desc]
                self.stdout.write(
                    f'  inativo_acerto_caixa: {"OK" if "inativo_acerto_caixa" in cols else "AUSENTE"}'
                )
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'  {exc}'))

        self.stdout.write(self.style.SUCCESS('\nSe houver AUSENTE ou migrate pendente: python manage.py migrate --noinput'))
