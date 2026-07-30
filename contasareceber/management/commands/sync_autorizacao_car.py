from django.core.management.base import BaseCommand

from contasareceber.socio_sync import sincronizar_autorizacao_car_da_nota


class Command(BaseCommand):
    help = (
        'Preenche autorização em Contas a Receber a partir da NFSe vinculada '
        '(campo nsu ou AUT/STONEID na discriminação).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa-id',
            type=int,
            help='Limitar à empresa (opcional).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra quantos registros seriam atualizados, sem gravar.',
        )

    def handle(self, *args, **options):
        stats = sincronizar_autorizacao_car_da_nota(
            empresa_id=options.get('empresa_id'),
            dry_run=options.get('dry_run'),
        )
        modo = 'Seriam atualizados' if options.get('dry_run') else 'Atualizados'
        self.stdout.write(
            self.style.SUCCESS(
                f'{modo}: {stats["notas_nsu"]} NFSe (nsu), '
                f'{stats["car"]} Conta(s) a Receber.'
            )
        )
        if stats['sem_auth']:
            self.stdout.write(
                f'CAR sem autorização e NF sem código detectável: {stats["sem_auth"]}'
            )
