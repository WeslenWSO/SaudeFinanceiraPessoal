"""Verifica MEDIA_ROOT (Render Disk) e lista anexos cujo arquivo físico não existe."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from faturamento_medico.services.media_storage import (
    diagnosticar_media_storage,
    gravar_marcador_teste_persistencia,
    ler_marcador_teste_persistencia,
)


class Command(BaseCommand):
    help = (
        'Diagnóstico de anexos PDF/imagem: MEDIA_ROOT gravável, contagem e lista de arquivos '
        'perdidos (reenviar manualmente). Use --gravar-teste e --ler-teste após redeploy.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa-id',
            type=int,
            help='Filtra anexos pela empresa do faturamento.',
        )
        parser.add_argument(
            '--limite',
            type=int,
            default=100,
            help='Máximo de anexos faltando listados (padrão 100).',
        )
        parser.add_argument(
            '--gravar-teste',
            action='store_true',
            help='Grava .render_media_test em MEDIA_ROOT (antes de um redeploy).',
        )
        parser.add_argument(
            '--ler-teste',
            action='store_true',
            help='Lê .render_media_test após redeploy (valida disco persistente).',
        )
        parser.add_argument(
            '--somente-faltando',
            action='store_true',
            help='Lista apenas anexos sem arquivo no disco.',
        )

    def handle(self, *args, **options):
        if options['gravar_teste']:
            ok, path, conteudo = gravar_marcador_teste_persistencia()
            if not ok:
                raise CommandError(f'Falha ao gravar teste: {conteudo}')
            self.stdout.write(self.style.SUCCESS(f'Marcador gravado: {path}'))
            self.stdout.write(conteudo)
            self.stdout.write(
                'Faça redeploy no Render e rode: python manage.py verificar_anexos_media --ler-teste'
            )
            return

        if options['ler_teste']:
            ok, msg = ler_marcador_teste_persistencia()
            if ok:
                self.stdout.write(self.style.SUCCESS('Disco persistente OK — marcador encontrado após deploy.'))
                self.stdout.write(msg)
            else:
                raise CommandError(msg)
            return

        status = diagnosticar_media_storage(
            empresa_id=options.get('empresa_id'),
            limite_faltando=options['limite'],
        )

        self.stdout.write('=== Armazenamento de anexos ===')
        self.stdout.write(f'MEDIA_ROOT: {status.media_root}')
        self.stdout.write(f'Existe: {status.exists} | Gravável: {status.writable}')
        self.stdout.write(f'Ambiente Render: {status.on_render}')
        self.stdout.write(f'Nota: {status.disk_mount_hint}')
        if status.write_error:
            self.stdout.write(self.style.ERROR(f'Erro gravação: {status.write_error}'))

        if not status.writable:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Render Dashboard → saude-financeira → Disks → mount /var/data (10 GB) '
                'e env MEDIA_ROOT=/var/data/media, depois Sync Blueprint / Manual Deploy.'
            ))

        if not options['somente_faltando']:
            self.stdout.write('')
            self.stdout.write(
                f'Anexos no banco: {status.total_anexos} | OK no disco: {status.anexos_ok} | '
                f'Faltando arquivo: {status.anexos_faltando}'
            )

        if status.faltando:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Anexos para REENVIAR (Detalhes -> Anexar):'))
            for item in status.faltando:
                self.stdout.write(
                    f"  doc #{item['documento_id']} | fat #{item['faturamento_id']} | "
                    f"{item['nome'][:60]}"
                )
            if status.anexos_faltando > len(status.faltando):
                self.stdout.write(
                    f'  … +{status.anexos_faltando - len(status.faltando)} não listados '
                    f'(aumente --limite)'
                )

        if status.writable and status.anexos_faltando == 0 and status.total_anexos > 0:
            self.stdout.write(self.style.SUCCESS('Todos os anexos do banco existem no disco.'))

        # Futuro S3 (plano opcional)
        use_s3 = getattr(settings, 'USE_S3_STORAGE', False)
        if use_s3:
            self.stdout.write('Storage S3/R2: ativo (USE_S3_STORAGE=true)')
        else:
            self.stdout.write(
                'Storage S3/R2: inativo (futuro: USE_S3_STORAGE=true + django-storages)'
            )

        if not status.writable:
            raise CommandError('MEDIA_ROOT não está gravável — configure disco persistente no Render.')
