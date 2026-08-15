#!/usr/bin/env python
"""
Atualiza faturamento médico Corpo de Bombeiro no Postgres (Render).

  set DATABASE_URL=postgresql://...
  python scripts/atualizar_faturamento_bombeiro.py --dry-run
  python scripts/atualizar_faturamento_bombeiro.py

Ou salve a URL em render_db.url na raiz do projeto (não versionar).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

CSV_DEFAULT = ROOT / 'scripts' / 'dados' / 'bombeiro_conferencia_jul2026.csv'


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--arquivo', type=Path, default=CSV_DEFAULT)
    parser.add_argument('--empresa-id', type=int, default=16)
    parser.add_argument('--convenio', default='CORPO DE BOMBEIRO')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if not args.arquivo.is_file():
        print(f'Arquivo não encontrado: {args.arquivo}', file=sys.stderr)
        return 1

    if not os.environ.get('DATABASE_URL'):
        url = ROOT / 'render_db.url'
        if url.is_file():
            os.environ['DATABASE_URL'] = url.read_text(encoding='utf-8').strip()
    if not os.environ.get('DATABASE_URL'):
        print('Defina DATABASE_URL (Render → Database → External Connection String).', file=sys.stderr)
        return 1

    import django
    django.setup()

    from django.core.management import call_command

    call_command(
        'atualizar_faturamento_bombeiro',
        arquivo=str(args.arquivo),
        empresa_id=args.empresa_id,
        convenio=args.convenio,
        dry_run=args.dry_run,
        verbosity=1,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
