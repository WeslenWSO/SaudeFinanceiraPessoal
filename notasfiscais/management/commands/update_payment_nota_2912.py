from django.core.management.base import BaseCommand
from notasfiscais.models import NotaFiscalServico
from cobranca.models import Cobranca

class Command(BaseCommand):
    help = 'Atualiza forma de pagamento da nota 2912 para CARTAO DEBITO e NSU 014072'

    def handle(self, *args, **options):
        # Busca a forma de pagamento CARTAO DEBITO
        try:
            cartao_debito = Cobranca.objects.get(descricao='CARTAO DEBITO', tpag='CD')
        except Cobranca.DoesNotExist:
            self.stdout.write(self.style.ERROR('Forma de pagamento "CARTAO DEBITO" não encontrada.'))
            return

        # Busca a nota 2912
        try:
            nota = NotaFiscalServico.objects.get(numero_nota='2912')
        except NotaFiscalServico.DoesNotExist:
            self.stdout.write(self.style.ERROR('Nota fiscal 2912 não encontrada.'))
            return

        # Atualiza a forma de pagamento e NSU
        nota.forma_pagamento = cartao_debito
        nota.nsu = '014072'
        nota.save()

        self.stdout.write(
            self.style.SUCCESS(f'Nota {nota.numero_nota} atualizada: Forma de pagamento "{cartao_debito.descricao}", NSU: {nota.nsu}')
        )