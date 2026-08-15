#!/usr/bin/env python
"""Alinha grid FUSEX jul/2026 conferido com planilha R$ 47.822,40."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
os.environ['DATABASE_URL'] = (ROOT / 'render_db.url').read_text(encoding='utf-8').strip()

import django
django.setup()

from faturamento_medico.models import FaturamentoMedico, ItemServico
from faturamento_medico.views import _aplicar_filtros_faturamento_qs

META = Decimal('47822.40')


def grid_total() -> tuple[int, Decimal]:
    filtros = {
        'nome': '', 'guia': '', 'anestesista': '', 'status': '',
        'status_conferencia': 'CONFERIDO', 'lote': '',
        'data_inicio': '2026-07-01', 'data_fim': '2026-07-31',
        'convenios': ['FUSEX'], 'codigo_relatorio': '',
    }
    qs = _aplicar_filtros_faturamento_qs(
        FaturamentoMedico.objects.filter(empresa_id=16), filtros
    ).prefetch_related('itens_servico')
    total = Decimal('0')
    n = 0
    for fat in qs:
        for item in fat.itens_servico.all():
            if not (item.conferido or item.status_conferencia == 'CONFERIDO'):
                continue
            total += Decimal(str(item.total if item.total is not None else item.valor or 0))
            n += 1
    return n, total


def conferir(item: ItemServico, valor: Decimal, servico: str | None = None) -> None:
    item.valor = valor
    if servico:
        item.servico = servico[:200]
    item.conferido = True
    item.status_conferencia = 'CONFERIDO'
    item.save()
    item.faturamento.atualizar_total()


def pendente(item: ItemServico) -> None:
    item.conferido = False
    item.status_conferencia = 'PENDENTE'
    item.save(update_fields=['conferido', 'status_conferencia'])
    item.faturamento.atualizar_total()


def criar_item(fat, servico, modalidade, valor):
    item = ItemServico(
        faturamento=fat,
        servico=servico[:200],
        modalidade=modalidade,
        valor=valor,
        qt=1,
        percentual=Decimal('1'),
        conferido=True,
        status_conferencia='CONFERIDO',
    )
    item.save()
    fat.atualizar_total()
    return item


def main() -> None:
    n0, t0 = grid_total()
    print(f'Antes: {n0} linhas | R$ {t0} | diff meta R$ {t0 - META}')

    # EDUARDO MAIA (guia 202611082)
    conferir(ItemServico.objects.get(id=24977), Decimal('1596.20'))
    pendente(ItemServico.objects.get(id=25396))  # joelho E duplicado
    fat_ed = ItemServico.objects.get(id=24978).faturamento
    if not fat_ed.itens_servico.filter(servico__icontains='Pelve').exists():
        criar_item(fat_ed, 'RM - Pelve (nao incluir articulacoes coxofemorais)', 'MR', Decimal('901.83'))

    # MARIA RAIMUNDA (guia 202610323)
    conferir(ItemServico.objects.get(id=23821), Decimal('189.70'))

    # RENATO (guia 202610694)
    conferir(ItemServico.objects.get(id=23273), Decimal('118.06'), 'US - Prostata (via abdominal)')
    conferir(ItemServico.objects.get(id=23271), Decimal('94.85'), 'US - Orgaos superficiais')

    # RUTE (guia 20269832) — remove duplicatas, adiciona faltantes
    pendente(ItemServico.objects.get(id=23219))
    pendente(ItemServico.objects.get(id=25395))
    fat_ru = ItemServico.objects.get(id=23216).faturamento
    if not fat_ru.itens_servico.filter(valor=Decimal('234.66')).exists():
        criar_item(fat_ru, 'US - TIREOIDE COM DOPPLER', 'US', Decimal('234.66'))
    org = fat_ru.itens_servico.filter(servico__icontains='superficiais').exclude(id=23219).first()
    if org:
        conferir(org, Decimal('94.85'))
    elif not fat_ru.itens_servico.filter(valor=Decimal('94.85'), servico__icontains='superficiais').exists():
        criar_item(fat_ru, 'US - Orgaos superficiais', 'US', Decimal('94.85'))

    # CARLOS — guia
    fat_c = ItemServico.objects.get(id=24271).faturamento
    if not (fat_c.guia or '').strip():
        fat_c.guia = '202610648'
        fat_c.save(update_fields=['guia'])

    # LUISA — fora da planilha
    pendente(ItemServico.objects.get(id=25393))

    n1, t1 = grid_total()
    print(f'Depois: {n1} linhas | R$ {t1} | diff meta R$ {t1 - META}')


if __name__ == '__main__':
    main()
