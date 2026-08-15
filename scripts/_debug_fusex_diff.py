#!/usr/bin/env python
"""Diagnóstico diferença FUSEX planilha vs sistema."""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
os.environ['DATABASE_URL'] = (ROOT / 'render_db.url').read_text(encoding='utf-8').strip()

import django
django.setup()

from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.services.atualizar_faturamento_convenio import (
    _ja_conferido_no_banco,
    _normalizar_guia,
    carregar_planilha,
)


def valor_item(item) -> Decimal:
    if item.total is not None:
        return Decimal(str(item.total))
    return Decimal(str(item.valor or 0))


def main() -> None:
    linhas = carregar_planilha(ROOT / 'scripts/dados/fusex_conferencia_jul2026.csv')
    total_plan = sum(l.valor for l in linhas)
    print(f'Planilha: {len(linhas)} linhas | R$ {total_plan}')

    conf_total = Decimal('0')
    conf_rows = []
    pend_total = Decimal('0')
    for fat in FaturamentoMedico.objects.filter(
        empresa_id=16, convenio='FUSEX', data__year=2026, data__month=7
    ).prefetch_related('itens_servico'):
        for item in fat.itens_servico.all():
            v = valor_item(item)
            if item.conferido or item.status_conferencia == 'CONFERIDO':
                conf_total += v
                conf_rows.append((fat, item, v))
            else:
                pend_total += v

    print(f'Sistema FUSEX CONFERIDO jul/2026: {len(conf_rows)} itens | R$ {conf_total}')
    print(f'Sistema FUSEX PENDENTE jul/2026: R$ {pend_total}')
    print(f'Diferença (sistema - planilha): R$ {conf_total - total_plan}')
    print()

    # Itens conferidos no sistema que não batem com nenhuma linha da planilha
    plan_matched_ids: set[int] = set()
    for linha in linhas:
        if not _ja_conferido_no_banco(linha, empresa_id=16, convenio='FUSEX'):
            print(f'PLANILHA SEM CONFERIDO: {linha.data} {linha.guia} {linha.paciente} R$ {linha.valor}')
            continue
        # encontrar item correspondente
        guia = _normalizar_guia(linha.guia)
        for fat, item, v in conf_rows:
            if item.id in plan_matched_ids:
                continue
            if fat.data != linha.data:
                continue
            if guia and _normalizar_guia(fat.guia or '') and guia != _normalizar_guia(fat.guia or ''):
                continue
            if (item.modalidade or '').upper() != linha.modalidade:
                continue
            if abs(v - linha.valor) > Decimal('0.02'):
                continue
            plan_matched_ids.add(item.id)
            break

    extras = [(fat, item, v) for fat, item, v in conf_rows if item.id not in plan_matched_ids]
    extra_total = sum(v for _, _, v in extras)
    print(f'Conferidos EXTRA (não na planilha): {len(extras)} | R$ {extra_total}')
    for fat, item, v in sorted(extras, key=lambda x: -x[2]):
        print(
            f'  #{item.id} | {fat.data:%d/%m/%Y} | guia {fat.guia or "-"} | '
            f'{fat.nome[:30]} | {item.modalidade} | R$ {v} | {(item.servico or "")[:45]}'
        )

    print()
    # Linhas planilha com valor diferente do item conferido
    print('=== VALOR PLANILHA ≠ SISTEMA (mesmo match lógico) ===')
    for linha in linhas:
        guia = _normalizar_guia(linha.guia)
        candidatos = []
        for fat, item, v in conf_rows:
            if fat.data != linha.data:
                continue
            if guia and _normalizar_guia(fat.guia or '') and guia != _normalizar_guia(fat.guia or ''):
                continue
            if (item.modalidade or '').upper() != linha.modalidade:
                continue
            candidatos.append((fat, item, v))
        if not candidatos:
            continue
        exact = [c for c in candidatos if abs(c[2] - linha.valor) <= Decimal('0.02')]
        if exact:
            continue
        for fat, item, v in candidatos:
            if abs(v - linha.valor) > Decimal('0.02'):
                print(
                    f'{linha.data:%d/%m/%Y} | guia {linha.guia} | {linha.paciente[:25]} | '
                    f'plan R$ {linha.valor} | sist R$ {v} | diff R$ {linha.valor - v} | #{item.id}'
                )
                break


if __name__ == '__main__':
    main()
