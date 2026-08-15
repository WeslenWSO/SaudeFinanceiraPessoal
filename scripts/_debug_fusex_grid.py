#!/usr/bin/env python
import os, sys
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
os.environ['DATABASE_URL'] = (ROOT / 'render_db.url').read_text(encoding='utf-8').strip()

import django
django.setup()

from faturamento_medico.models import FaturamentoMedico, ItemServico
from faturamento_medico.views import _aplicar_filtros_faturamento_qs
from faturamento_medico.services.atualizar_faturamento_convenio import (
    carregar_planilha, _buscar_item, _ja_conferido_no_banco, _normalizar_guia,
)


def v(item):
    return Decimal(str(item.total if item.total is not None else item.valor or 0))


filtros = {
    'nome': '', 'guia': '', 'anestesista': '', 'status': '',
    'status_conferencia': 'CONFERIDO', 'lote': '',
    'data_inicio': '2026-07-01', 'data_fim': '2026-07-31',
    'convenios': ['FUSEX'], 'codigo_relatorio': '',
}
qs = _aplicar_filtros_faturamento_qs(
    FaturamentoMedico.objects.filter(empresa_id=16).order_by('-data'), filtros
)
qs = qs.prefetch_related('itens_servico')

grid_ids = set()
grid_total = Decimal('0')
for fat in qs:
    for item in fat.itens_servico.all():
        if not (item.conferido or item.status_conferencia == 'CONFERIDO'):
            continue
        grid_ids.add(item.id)
        grid_total += v(item)

linhas = carregar_planilha(ROOT / 'scripts/dados/fusex_conferencia_jul2026.csv')
total_plan = sum(l.valor for l in linhas)
print(f'Planilha: {len(linhas)} R$ {total_plan}')
print(f'Grid: {len(grid_ids)} linhas R$ {grid_total}')
print(f'Diff: R$ {total_plan - grid_total}')
print()

# planilha lines not represented in grid (by item match)
ids_usados = set()
missing = []
for linha in linhas:
    item = None
    if _ja_conferido_no_banco(linha, empresa_id=16, convenio='FUSEX'):
        # find conferido item
        from faturamento_medico.services import atualizar_faturamento_convenio as svc
        for cand in svc._candidatos_query(linha, empresa_id=16, convenio='FUSEX', apenas_pendentes=False):
            if not (cand.conferido or cand.status_conferencia == 'CONFERIDO'):
                continue
            if not svc._paciente_compativel(linha, cand.faturamento):
                continue
            if cand.id in ids_usados:
                continue
            score = svc._score_item(linha, cand)
            if score >= 5.0 and abs(v(cand) - linha.valor) <= Decimal('0.02'):
                item = cand
                ids_usados.add(cand.id)
                break
    if item is None:
        missing.append((linha, None, 'sem item'))
    elif item.id not in grid_ids:
        missing.append((linha, item, 'fora do grid'))

print('=== PLANILHA FORA DO GRID ===')
for linha, item, motivo in missing:
    extra = f'item #{item.id} R$ {v(item)}' if item else motivo
    print(f'{linha.data:%d/%m/%Y} | guia {linha.guia} | {linha.paciente[:28]} | R$ {linha.valor} | {extra}')

print()
print('=== GRID FORA DA PLANILHA ===')
plan_ids = ids_usados
for iid in sorted(grid_ids - plan_ids):
    item = ItemServico.objects.select_related('faturamento').get(id=iid)
    fat = item.faturamento
    print(f'#{iid} | {fat.data:%d/%m/%Y} | guia {fat.guia} | {fat.nome[:28]} | R$ {v(item)} | {(item.servico or "")[:40]}')
