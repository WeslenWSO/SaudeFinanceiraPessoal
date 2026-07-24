from django.core.management.base import BaseCommand
from notasfiscais.models import NotaFiscalServico
from cobranca.models import Cobranca

class Command(BaseCommand):
    help = 'Atualiza forma de pagamento da nota 2923 para DINHEIRO'

    def handle(self, *args, **options):
        # Busca a forma de pagamento DINHEIRO
        try:
            dinheiro = Cobranca.objects.get(descricao='DINHEIRO', tpag='DH')
        except Cobranca.DoesNotExist:
            self.stdout.write(self.style.ERROR('Forma de pagamento "DINHEIRO" não encontrada.'))
            return

        # Busca a nota 2923
        try:
            nota = NotaFiscalServico.objects.get(numero_nota='2923')
        except NotaFiscalServico.DoesNotExist:
            self.stdout.write(self.style.ERROR('Nota fiscal 2923 não encontrada.'))
            return

        # Atualiza a forma de pagamento
        nota.forma_pagamento = dinheiro
        nota.save()

        self.stdout.write(
            self.style.SUCCESS(f'Forma de pagamento da nota {nota.numero_nota} atualizada para "{dinheiro.descricao}".')
        )