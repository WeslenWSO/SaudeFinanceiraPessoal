"""Corrige sequences Postgres das tabelas OPCARTAO (evita duplicate key no import)."""
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection

from OPCARTAO.models import CartaoCredito, FaturaCartaoCredito, ItemFaturaCartao, Opcartao


class Command(BaseCommand):
    help = 'Reseta sequences de ID das tabelas OPCARTAO para MAX(id).'

    def handle(self, *args, **options):
        models = [ItemFaturaCartao, FaturaCartaoCredito, CartaoCredito, Opcartao]
        sqls = connection.ops.sequence_reset_sql(no_style(), models)
        if not sqls:
            self.stdout.write('Nenhum SQL de sequence (banco não usa sequences).')
            return
        with connection.cursor() as cur:
            for sql in sqls:
                self.stdout.write(sql)
                cur.execute(sql)
            for model in models:
                table = model._meta.db_table
                cur.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
                max_id = cur.fetchone()[0]
                self.stdout.write(self.style.SUCCESS(f'{table}: max_id={max_id}'))
        self.stdout.write(self.style.SUCCESS('Sequences OPCARTAO corrigidas.'))
