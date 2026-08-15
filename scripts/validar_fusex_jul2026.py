#!/usr/bin/env python
"""Valida planilha vs sistema e opcionalmente marca CONFERIDO."""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

if not os.environ.get('DATABASE_URL'):
    url = ROOT / 'render_db.url'
    if url.is_file():
        os.environ['DATABASE_URL'] = url.read_text(encoding='utf-8').strip()

import django
django.setup()

from faturamento_medico.services.atualizar_faturamento_convenio import (
    _buscar_item,
    _ja_conferido_no_banco,
    _normalizar_guia,
    _normalizar_texto,
    aplicar_atualizacoes,
    carregar_planilha,
)


def valor_item_db(item) -> Decimal:
    if item.total is not None:
        return Decimal(str(item.total))
    return Decimal(str(item.valor or 0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--arquivo', type=Path, default=ROOT / 'scripts/dados/fusex_conferencia_jul2026.csv')
    parser.add_argument('--empresa-id', type=int, default=16)
    parser.add_argument('--convenio', default='FUSEX')
    parser.add_argument('--aplicar', action='store_true', help='Grava conferência no banco')
    args = parser.parse_args()

    linhas = carregar_planilha(args.arquivo)
    total_plan = sum(l.valor for l in linhas)
    print(f'Planilha: {len(linhas)} linhas | Total R$ {total_plan:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print()

    ids_usados: set[int] = set()
    ja_conferido = []
    atualizar = []
    valor_diff = []
    nao_encontrados = []

    for linha in linhas:
        if _ja_conferido_no_banco(linha, empresa_id=args.empresa_id, convenio=args.convenio):
            ja_conferido.append(linha)
            continue
        item = _buscar_item(linha, empresa_id=args.empresa_id, convenio=args.convenio, ids_usados=ids_usados)
        if item is None:
            nao_encontrados.append(linha)
            continue
        vdb = valor_item_db(item)
        if abs(vdb - linha.valor) > Decimal('0.02'):
            valor_diff.append((linha, item, vdb))
        atualizar.append((linha, item))
        ids_usados.add(item.id)

    total_ja = sum(l.valor for l in ja_conferido)
    total_atualizar = sum(l.valor for _, l in [(x, x[0]) for x in atualizar] if False)
    total_atualizar = sum(l.valor for l, _ in atualizar)
    total_nao = sum(l.valor for l in nao_encontrados)

    print('=== RESUMO ===')
    print(f'Já CONFERIDO no sistema: {len(ja_conferido)} linhas | R$ {total_ja:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print(f'A conferir (match encontrado): {len(atualizar)} linhas | R$ {total_atualizar:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print(f'NÃO ENCONTRADO: {len(nao_encontrados)} linhas | R$ {total_nao:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print(f'Diferença de valor (match com valor distinto): {len(valor_diff)}')
    coberto = total_ja + total_atualizar + total_nao
    print(f'Soma categorias: R$ {coberto:,.2f} (planilha R$ {total_plan:,.2f})'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print()

    if valor_diff:
        print('=== VALOR DIFERENTE (planilha vs sistema) ===')
        for linha, item, vdb in valor_diff[:30]:
            fat = item.faturamento
            print(
                f'{linha.data:%d/%m/%Y} | guia {linha.guia} | {linha.paciente[:35]} | '
                f'plan R$ {linha.valor} | sist R$ {vdb} | diff R$ {linha.valor - vdb} | '
                f'item #{item.id} | {(item.servico or "")[:50]}'
            )
        if len(valor_diff) > 30:
            print(f'... +{len(valor_diff) - 30} linhas')
        print()

    if nao_encontrados:
        print('=== NÃO ENCONTRADO NO SISTEMA ===')
        for linha in nao_encontrados:
            print(
                f'{linha.data:%d/%m/%Y} | guia {linha.guia} | {linha.paciente} | '
                f'{linha.modalidade} | R$ {linha.valor} | {(linha.procedimento or "")[:55]}'
            )
        print()

    if atualizar:
        print('=== SERÃO MARCADOS CONFERIDO ===')
        for linha, item in atualizar[:25]:
            fat = item.faturamento
            vdb = valor_item_db(item)
            extra = f' (valor {vdb} -> {linha.valor})' if abs(vdb - linha.valor) > Decimal('0.02') else ''
            print(
                f'item #{item.id} fat #{fat.id} | {linha.data:%d/%m/%Y} | guia {linha.guia} | '
                f'{linha.paciente[:30]} | R$ {linha.valor}{extra}'
            )
        if len(atualizar) > 25:
            print(f'... +{len(atualizar) - 25} linhas')
        print()

    if args.aplicar:
        print('=== APLICANDO ===')
        stats = aplicar_atualizacoes(
            linhas,
            empresa_id=args.empresa_id,
            convenio=args.convenio,
            dry_run=False,
        )
        print(
            f"Atualizados: {stats['atualizados']} | "
            f"Já conferidos: {stats['ja_conferidos_banco']} | "
            f"Não encontrados: {stats['nao_encontrados']} | Erros: {stats['erros']}"
        )
        for d in stats['detalhes']:
            if d.startswith('NÃO') or d.startswith('ERRO') or d.startswith('OK'):
                print(d)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
