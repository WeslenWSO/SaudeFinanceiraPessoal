import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = (ROOT / 'render_db.url').read_text(encoding='utf-8').strip()

import django
django.setup()

from faturamento_medico.models import ItemServico

for d in [date(2026, 7, 17), date(2026, 7, 18), date(2026, 7, 21), date(2026, 7, 22), date(2026, 7, 25), date(2026, 7, 27), date(2026, 7, 29)]:
    qs = ItemServico.objects.filter(
        faturamento__empresa_id=16,
        faturamento__data=d,
        faturamento__convenio__icontains='BOMBEIRO',
    ).exclude(status_conferencia='CONFERIDO').exclude(conferido=True)
    print(f'=== {d:%d/%m/%Y} pendentes={qs.count()}')
    for i in qs:
        f = i.faturamento
        print(f'  #{i.id} {f.nome} | {i.modalidade} | R${i.valor} | {i.servico[:50] if i.servico else ""}')
