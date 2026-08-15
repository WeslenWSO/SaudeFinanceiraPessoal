#!/usr/bin/env python
import os, sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
os.environ['DATABASE_URL'] = (ROOT / 'render_db.url').read_text(encoding='utf-8').strip()

import django
django.setup()

from faturamento_medico.models import FaturamentoMedico, Lote
from faturamento_medico.views import _aplicar_filtros_faturamento_qs

META = Decimal('47822.40')
LOTE_TOTAL = Decimal('49002.02')


def v(item):
    return Decimal(str(item.total if item.total is not None else item.valor or 0))


def main():
    lote = Lote.objects.get(id=7, empresa_id=16)
    print(f'Lote 7: {lote.convenio} | total_lote R$ {lote.total_lote}')
    print(f'Planilha jul/2026: R$ {META}')
    print(f'Diferenca lote - planilha: R$ {lote.total_lote - META}')
    print()

    fats = FaturamentoMedico.objects.filter(empresa_id=16, lote='7').prefetch_related('itens_servico')
    conf = pend = Decimal('0')
    fat_sum = Decimal('0')
    for f in fats:
        fat_sum += Decimal(str(f.total or 0))
        for i in f.itens_servico.all():
            val = v(i)
            if i.conferido or i.status_conferencia == 'CONFERIDO':
                conf += val
            else:
                pend += val

    print(f'Faturamentos no lote: {fats.count()}')
    print(f'Soma faturamento.total (como o lote calcula): R$ {fat_sum}')
    print(f'Soma itens CONFERIDO no lote: R$ {conf}')
    print(f'Soma itens PENDENTE no lote: R$ {pend}')
    print(f'Extra no lote vs planilha (conferido): R$ {conf - META}')
    print()

    print('=== ITENS PENDENTES DENTRO DO LOTE 7 ===')
    for f in fats:
        for i in f.itens_servico.all():
            if i.conferido or i.status_conferencia == 'CONFERIDO':
                continue
            print(
                f'  #{i.id} fat#{f.id} {f.data:%d/%m/%Y} {f.nome[:25]} | '
                f'{i.modalidade} R$ {v(i)} | {i.status_conferencia} | {(i.servico or "")[:40]}'
            )

    print()
    print('=== CONFERIDOS NO LOTE 7 FORA DO FILTRO jul/2026 ===')
    for f in fats:
        if f.data.year == 2026 and f.data.month == 7:
            continue
        for i in f.itens_servico.all():
            if i.conferido or i.status_conferencia == 'CONFERIDO':
                print(f'  #{i.id} {f.data:%d/%m/%Y} {f.nome[:25]} R$ {v(i)}')

    # Grid conferido jul not in lote
    filtros = {
        'nome': '', 'guia': '', 'anestesista': '', 'status': '',
        'status_conferencia': 'CONFERIDO', 'lote': '',
        'data_inicio': '2026-07-01', 'data_fim': '2026-07-31',
        'convenios': ['FUSEX'], 'codigo_relatorio': '',
    }
    qs = _aplicar_filtros_faturamento_qs(
        FaturamentoMedico.objects.filter(empresa_id=16), filtros
    ).prefetch_related('itens_servico')
    fora_lote = Decimal('0')
    print()
    print('=== CONFERIDOS jul/2026 FUSEX SEM LOTE (fora do lote 7) ===')
    for f in qs:
        if str(f.lote or '') == '7':
            continue
        for i in f.itens_servico.all():
            if not (i.conferido or i.status_conferencia == 'CONFERIDO'):
                continue
            val = v(i)
            fora_lote += val
            print(f'  #{i.id} fat#{f.id} lote={f.lote!r} {f.data:%d/%m/%Y} {f.nome[:22]} R$ {val}')
    print(f'Total conferido jul FUSEX fora lote 7: R$ {fora_lote}')


if __name__ == '__main__':
    main()
