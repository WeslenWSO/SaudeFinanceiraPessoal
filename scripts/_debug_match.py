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

from django.db.models import Q
from faturamento_medico.models import ItemServico


def show(data, nome_part):
    qs = ItemServico.objects.filter(
        faturamento__empresa_id=16,
        faturamento__data=data,
        faturamento__convenio__icontains='BOMBEIRO',
    ).filter(
        Q(faturamento__nome__icontains=nome_part) | Q(faturamento__nome_associado__icontains=nome_part)
    )
    print(f'=== {data} | {nome_part} | total={qs.count()}')
    for i in qs[:10]:
        f = i.faturamento
        srv = (i.servico or '')[:60]
        print(
            f'  item={i.id} conf={i.conferido}/{i.status_conferencia} '
            f'nome={f.nome!r} assoc={f.nome_associado!r} mod={i.modalidade} val={i.valor} srv={srv!r}'
        )


show(date(2026, 7, 16), 'ANA')
show(date(2026, 7, 16), 'MAURO')
show(date(2026, 7, 16), 'GENELCI')
show(date(2026, 7, 22), 'IARLLI')
show(date(2026, 7, 28), 'MAICO')
show(date(2026, 7, 28), 'EVANGELISTA')
show(date(2026, 7, 28), 'LAURA')
