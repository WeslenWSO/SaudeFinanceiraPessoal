"""Verifica Gemini em producao (Postgres Render) — nao imprime chave completa."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def mask(key: str) -> str:
    key = (key or '').strip()
    if not key:
        return '(vazia)'
    if len(key) <= 8:
        return '***'
    return f'{key[:4]}...{key[-4:]}'


def main() -> int:
    db_url_file = ROOT / 'render_db.url'
    if not db_url_file.is_file():
        print('render_db.url nao encontrado.')
        return 1

    os.environ['DATABASE_URL'] = db_url_file.read_text(encoding='utf-8').strip()
    os.environ.pop('GEMINI_API_KEY', None)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

    import django

    django.setup()

    from dashboard.models import GeminiConfig
    from SaudeFinanceira.gemini_config import get_gemini_api_key, get_gemini_model

    cfg = GeminiConfig.objects.filter(pk=1).first()
    db_key = (cfg.api_key or '').strip() if cfg else ''
    db_model = (cfg.model_name or '').strip() if cfg else ''

    resolved = get_gemini_api_key()
    model = get_gemini_model()

    print('=== Postgres producao (financas-db / GeminiConfig) ===')
    print(f'registro_existe: {bool(cfg)}')
    print(f'api_key: {mask(db_key)}')
    print(f'model_name: {db_model or "gemini-2.5-flash (padrao)"}')
    if cfg and cfg.atualizado_em:
        print(f'atualizado_em: {cfg.atualizado_em}')

    print()
    print('=== Chave que o app usaria SEM GEMINI_API_KEY no Render ===')
    print(f'get_gemini_api_key(): {mask(resolved)}')
    print(f'get_gemini_model(): {model}')
    print(f'configurada: {"SIM" if resolved else "NAO"}')

    env_file = ROOT / '.env'
    local_key = ''
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = re.match(r'^\s*GEMINI_API_KEY\s*=\s*(.+)\s*$', line)
            if m:
                local_key = m.group(1).strip().strip('"').strip("'")

    print()
    print('=== Referencia (.env local) ===')
    print(f'GEMINI_API_KEY local: {mask(local_key)}')
    print()
    print('Nota: variavel GEMINI_API_KEY no painel Render nao foi consultada')
    print('(CLI Render expirada). Prioridade em producao: env Render > Postgres.')

    return 0 if resolved else 2


if __name__ == '__main__':
    raise SystemExit(main())
