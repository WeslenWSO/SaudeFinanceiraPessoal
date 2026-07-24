from django.core.management.base import BaseCommand
from notasfiscais.models import NotaFiscalServico

class Command(BaseCommand):
    help = 'Recalcula o ISS Apuração para todas as NFSe'

    def handle(self, *args, **options):
        notas = NotaFiscalServico.objects.all()
        count = 0
        for nota in notas:
            old_value = nota.issapuracao
            nota.save()  # Isso irá recalcular o ISS Apuração
            if nota.issapuracao != old_value:
                count += 1
                self.stdout.write(
                    f'Nota {nota.numero_nota}: ISS Apuração alterado de {old_value} para {nota.issapuracao}'
                )
        self.stdout.write(
            self.style.SUCCESS(f'Recalculado ISS Apuração para {count} notas de {notas.count()} total')
        )