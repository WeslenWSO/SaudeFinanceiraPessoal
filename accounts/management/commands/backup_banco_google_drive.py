"""Backup PostgreSQL + upload para Google Drive (pasta BKP_SAUDE). Uso: cron Render ou manual."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.backup_banco import criar_backup_completo
from accounts.backup_google_drive import drive_configurado, enviar_arquivo_para_drive


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

    def handle(self, *args, **options):
        if options['agendado']:
            from accounts.backup_config import slot_backup_para_executar_agora

            slot = slot_backup_para_executar_agora()
            if slot is None:
                self.stdout.write('Fora do horário de backup agendado — nada a fazer.')
                return

            self.stdout.write(
                f'Executando backup agendado (slot {slot.strftime("%H:%M")}).'
            )

        info = criar_backup_completo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Backup local: {info['arquivo']} ({info['formato']}, {info['tamanho']} bytes)"
            )
        )

        if options['somente_local']:
            return

        if not drive_configurado():
            self.stdout.write(
                self.style.WARNING(
                    'Google Drive não configurado — backup ficou só no servidor. '
                    'Configure BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON e compartilhe a pasta '
                    'BKP_SAUDE com o e-mail da service account.'
                )
            )
            return

        caminho = info.get('caminho') or ''
        if not caminho:
            raise RuntimeError('Caminho do backup não retornado.')

        up = enviar_arquivo_para_drive(caminho)
        self.stdout.write(
            self.style.SUCCESS(
                f"Enviado ao Drive: {up.get('name')} (id={up.get('file_id')})"
            )
        )
