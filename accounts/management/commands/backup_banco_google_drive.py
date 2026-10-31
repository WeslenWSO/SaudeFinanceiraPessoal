"""Backup PostgreSQL + upload para Google Drive (pasta BKP_SAUDE). Uso: cron Render ou manual."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounts.backup_runner import executar_backup_google_drive


class Command(BaseCommand):
    help = (
        'Gera backup do banco (pg_dump ou dumpdata) e envia para o Google Drive '
        '(pasta BKP_SAUDE / BACKUP_GOOGLE_DRIVE_FOLDER_ID).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--somente-local',
            action='store_true',
            help='Só grava na pasta BACKUP_DATABASE_DIR, sem upload.',
        )
        parser.add_argument(
            '--agendado',
            action='store_true',
            help='Só executa se estiver no horário configurado (uso: cron a cada hora).',
        )
        parser.add_argument(
            '--forcar',
            action='store_true',
            help='Ignora horário agendado (teste no Shell do Render).',
        )

    def handle(self, *args, **options):
        if options['somente_local']:
            from accounts.backup_banco import criar_backup_completo

            info = criar_backup_completo()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backup local: {info['arquivo']} ({info['formato']}, {info['tamanho']} bytes)"
                )
            )
            return

        modo = 'manual'
        if options['agendado']:
            modo = 'agendado'
        elif options['forcar']:
            modo = 'forcar'

        try:
            result = executar_backup_google_drive(modo=modo)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if result.get('pulou'):
            self.stdout.write(result.get('mensagem', 'Nada a fazer.'))
            return

        if result.get('ok'):
            self.stdout.write(self.style.SUCCESS(result.get('mensagem', 'OK')))
        else:
            self.stdout.write(self.style.WARNING(result.get('mensagem', 'Falha parcial.')))
