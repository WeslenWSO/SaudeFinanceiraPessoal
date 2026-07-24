from django.core.management.base import BaseCommand
from cobranca.models import Cobranca

class Command(BaseCommand):
    help = 'Adiciona forma de pagamento em espécie (dinheiro)'

    def handle(self, *args, **options):
        # Lista formas de pagamento existentes
        self.stdout.write('Formas de pagamento existentes:')
        for cob in Cobranca.objects.all():
            self.stdout.write(f'  - {cob.descricao} (Tipo: {cob.formapgto}, TPag: {cob.tpag})')

        # Verifica se já existe
        if Cobranca.objects.filter(descricao='Dinheiro', tpag='DH').exists():
            self.stdout.write(self.style.WARNING('Forma de pagamento "Dinheiro" já existe.'))
            return

        # Cria a forma de pagamento
        cobranca = Cobranca.objects.create(
            formapgto='0',  # A VISTA
            descricao='Dinheiro',
            tpag='DH'
        )

        self.stdout.write(
            self.style.SUCCESS(f'Forma de pagamento "{cobranca.descricao}" criada com sucesso!')
        )