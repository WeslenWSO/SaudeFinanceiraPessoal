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
        parser.add_argument(
            '--reprocessar-nf',
            action='store_true',
            help='Relê discriminação das NFS-e antes de propagar para o CAR.',
        )

    def handle(self, *args, **options):
        empresa_id = options.get('empresa_id')
        if options.get('reprocessar_nf') and empresa_id and not options.get('dry_run'):
            from contasareceber.nf_sync_discriminacao import reprocessar_aut_nf_empresa_periodo

            rep = reprocessar_aut_nf_empresa_periodo(empresa_id)
            self.stdout.write(
                f'NFs reprocessadas: {rep["notas_processadas"]}, '
                f'CAR com AUT: {rep["car_aut"]}.'
            )
        stats = sincronizar_autorizacao_car_da_nota(
            empresa_id=empresa_id,
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
