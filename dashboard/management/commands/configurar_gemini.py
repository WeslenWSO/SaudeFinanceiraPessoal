"""Grava a chave Gemini no Postgres (fallback para produção sem variável de ambiente)."""
from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from dashboard.models import GeminiConfig


def _carregar_dotenv() -> None:
    env_path = Path(settings.BASE_DIR) / '.env'
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


class Command(BaseCommand):
    help = 'Configura GeminiConfig no banco (lê .env ou variáveis de ambiente).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-env',
            action='store_true',
            help='Lê GEMINI_API_KEY e GEMINI_MODEL do ambiente ou .env local.',
        )
        parser.add_argument('--api-key', default='')
        parser.add_argument('--model', default='')

    def handle(self, *args, **options):
        _carregar_dotenv()

        api_key = (options.get('api_key') or '').strip()
        model = (options.get('model') or '').strip()

        if options.get('from_env') or (not api_key and not model):
            api_key = api_key or (os.environ.get('GEMINI_API_KEY') or '').strip()
            model = model or (os.environ.get('GEMINI_MODEL') or '').strip()

        if not api_key:
            self.stderr.write(
                'Informe --api-key ou use --from-env com GEMINI_API_KEY no .env / ambiente.'
            )
            return

        if not model:
            model = 'gemini-2.5-flash'

        obj = GeminiConfig.get_solo()
        obj.api_key = api_key
        obj.model_name = model
        obj.save(update_fields=['api_key', 'model_name', 'atualizado_em'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Gemini configurado no banco (modelo={model}, chave=***{api_key[-4:]}).'
            )
        )
