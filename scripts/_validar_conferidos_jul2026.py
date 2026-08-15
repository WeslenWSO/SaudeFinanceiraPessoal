#!/usr/bin/env python
"""Compara conferidos Bombeiro jul/2026 no banco vs planilha de referência."""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date
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

from django.db.models import Q, Sum
from faturamento_medico.models import FaturamentoMedico, ItemServico

EMPRESA_ID = 16
CONVENIO = 'CORPO DE BOMBEIRO'
DATA_INI = date(2026, 7, 1)
DATA_FIM = date(2026, 7, 31)

# Planilha completa jul/2026 (imagem do usuário)
PLANILHA = [
    ('01/07/2026', 'DEISE PEREIRA DO NASCIMENTO', 'US', Decimal('200.00')),
    ('01/07/2026', 'DEISE PEREIRA DO NASCIMENTO', 'US', Decimal('40.00')),
    ('01/07/2026', 'JOSE NALDO DE SOUZA FREITAS', 'US', Decimal('200.00')),
    ('06/07/2026', 'YASMIM FURTADO COELHO', 'EC', Decimal('60.00')),
    ('08/07/2026', 'GILMAR TORRES MARQUES MOURA', 'MR', Decimal('900.00')),
    ('08/07/2026', 'SEBASTIAO MENDONCA GOES', 'MR', Decimal('800.00')),
    ('28/07/2026', 'SEBASTIAO MENDONCA GOES', 'US', Decimal('110.00')),
    ('09/07/2026', 'VANDERNILSON PERES DA SILVA', 'CT', Decimal('350.00')),
    ('13/07/2026', 'IZABEL OLIVEIRA DA SILVA BRITO', 'CT', Decimal('350.00')),
    ('14/07/2026', 'LUZIA NASCIMENTO RODRIGUES', 'US', Decimal('110.00')),
    ('14/07/2026', 'LUZIA NASCIMENTO RODRIGUES', 'US', Decimal('110.00')),
    ('14/07/2026', 'LUZIA NASCIMENTO RODRIGUES', 'US', Decimal('110.00')),
    ('14/07/2026', 'JANETE TAINA NASCIMENTO RODRIGUES', 'US', Decimal('110.00')),
    ('14/07/2026', 'JANETE TAINA NASCIMENTO RODRIGUES', 'US', Decimal('110.00')),
    ('14/07/2026', 'JANETE TAINA NASCIMENTO RODRIGUES', 'US', Decimal('110.00')),
    ('15/07/2026', 'MANOEL JOSE DE SOUZA', 'US', Decimal('110.00')),
    ('16/07/2026', 'ANA LUISA ALMEIDA LIMA', 'US', Decimal('110.00')),
    ('16/07/2026', 'ANA LUISA ALMEIDA LIMA', 'US', Decimal('110.00')),
    ('16/07/2026', 'ANA LUISA ALMEIDA LIMA', 'US', Decimal('110.00')),
    ('16/07/2026', 'ANA LUISA ALMEIDA LIMA', 'US', Decimal('110.00')),
    ('16/07/2026', 'GENELCI DE OLIVEIRA DA SILVA', 'US', Decimal('110.00')),
    ('17/07/2026', 'LUMA RIBEIRO PANTOJA MARQUES', 'MR', Decimal('900.00')),
    ('18/07/2026', 'AUDICELIA DA SILVA VALENTE', 'MR', Decimal('1700.00')),
    ('21/07/2026', 'LUEILI SOUZA DE OLIVEIRA BATISTA', 'MR', Decimal('1300.00')),
    ('22/07/2026', 'IARLLI LEANDRO SOARES DE SOUZA', 'CR', Decimal('40.00')),
    ('22/07/2026', 'IARLLI LEANDRO SOARES DE SOUZA', 'CR', Decimal('40.00')),
    ('22/07/2026', 'IARLLI LEANDRO SOARES DE SOUZA', 'CR', Decimal('70.00')),
    ('22/07/2026', 'THAISLA DE JESUS SILVA VALENTE', 'US', Decimal('110.00')),
    ('25/07/2026', 'MARCELA SARKIS SOPCHAKI', 'MR', Decimal('800.00')),
    ('25/07/2026', 'MARCELA SARKIS SOPCHAKI', 'MR', Decimal('800.00')),
    ('25/07/2026', 'MARCELA SARKIS SOPCHAKI', 'MR', Decimal('800.00')),
    ('25/07/2026', 'MARCELA SARKIS SOPCHAKI', 'MR', Decimal('800.00')),
    ('28/07/2026', 'MARCELA SARKIS SOPCHAKI', 'CR', Decimal('40.00')),
    ('28/07/2026', 'MARCELA SARKIS SOPCHAKI', 'CR', Decimal('40.00')),
    ('28/07/2026', 'MARCELA SARKIS SOPCHAKI', 'CR', Decimal('40.00')),
    ('27/07/2026', 'MAICO NAIT LUCAS CARDOSO', 'MR', Decimal('800.00')),
    ('28/07/2026', 'MAICO NAIT LUCAS CARDOSO', 'US', Decimal('110.00')),
    ('28/07/2026', 'MAICO NAIT LUCAS CARDOSO', 'CR', Decimal('50.00')),
    ('28/07/2026', 'EVANGELISTA FERREIRA MOREIRA', 'US', Decimal('110.00')),
    ('28/07/2026', 'LAURA DA SILVA MELO', 'US', Decimal('110.00')),
    ('29/07/2026', 'RONIA MATIAS CASSIANO', 'MR', Decimal('1600.00')),
    ('29/07/2026', 'RONIA MATIAS CASSIANO', 'MR', Decimal('900.00')),
    ('29/07/2026', 'RONIA MATIAS CASSIANO', 'MR', Decimal('700.00')),
]


def norm(s: str) -> str:
    import unicodedata, re
    t = (s or '').strip().upper()
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t)


def valor_item(item: ItemServico) -> Decimal:
    if item.total is not None:
        return Decimal(str(item.total))
    return Decimal(str(item.valor or 0))


def main() -> None:
    fats = FaturamentoMedico.objects.filter(
        empresa_id=EMPRESA_ID,
        convenio__icontains='BOMBEIRO',
        data__gte=DATA_INI,
        data__lte=DATA_FIM,
    ).prefetch_related('itens_servico')

    conferidos = []
    pendentes = []
    outros_status = []

    for fat in fats:
        itens = list(fat.itens_servico.all())
        if not itens:
            continue
        for item in itens:
            v = valor_item(item)
            row = {
                'item_id': item.id,
                'fat_id': fat.id,
                'data': fat.data,
                'paciente': fat.nome or '',
                'modalidade': (item.modalidade or '').upper(),
                'valor': v,
                'status': item.status_conferencia,
                'conferido': item.conferido,
                'procedimento': item.servico or '',
            }
            if item.conferido or item.status_conferencia == 'CONFERIDO':
                conferidos.append(row)
            elif item.status_conferencia in ('', 'PENDENTE'):
                pendentes.append(row)
            else:
                outros_status.append(row)

    total_planilha = sum(v for *_, v in PLANILHA)
    total_conferidos = sum(r['valor'] for r in conferidos)
    total_pendentes = sum(r['valor'] for r in pendentes)

    print(f'Planilha: {len(PLANILHA)} linhas | Total R$ {total_planilha:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print(f'Sistema CONFERIDO: {len(conferidos)} itens | Total R$ {total_conferidos:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print(f'Sistema PENDENTE: {len(pendentes)} itens | Total R$ {total_pendentes:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    diff = total_planilha - total_conferidos
    print(f'Diferença (planilha - conferidos): R$ {diff:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print()

    # Chave multiset para comparar
    def key(data_str, pac, mod, val):
        return (data_str, norm(pac), mod, val)

    from datetime import datetime
    plan_counts = defaultdict(int)
    for d, p, m, v in PLANILHA:
        dt = datetime.strptime(d, '%d/%m/%Y').date()
        plan_counts[(dt, norm(p), m, v)] += 1

    conf_counts = defaultdict(list)
    for r in conferidos:
        k = (r['data'], norm(r['paciente']), r['modalidade'], r['valor'])
        conf_counts[k].append(r)

    print('=== NA PLANILHA, AUSENTE OU VALOR DIFERENTE NO CONFERIDO ===')
    for k in sorted(plan_counts.keys()):
        need = plan_counts[k]
        have = conf_counts.get(k, [])
        if len(have) < need:
            dt, pac, mod, val = k
            print(f'FALTA {need - len(have)}x | {dt:%d/%m/%Y} | {pac} | {mod} | R$ {val}')

    print()
    print('=== CONFERIDOS NO SISTEMA FORA DA PLANILHA (mesma chave) ===')
    for k, rows in sorted(conf_counts.items()):
        need = plan_counts.get(k, 0)
        if len(rows) > need:
            dt, pac, mod, val = k
            for r in rows[need:]:
                print(f'EXTRA | item #{r["item_id"]} fat #{r["fat_id"]} | {dt:%d/%m/%Y} | {pac} | {mod} | R$ {val} | {r["procedimento"][:60]}')

    print()
    print('=== CONFERIDOS CT jul/2026 (tomografia) ===')
    for r in sorted(conferidos, key=lambda x: (x['data'], x['paciente'])):
        if r['modalidade'] == 'CT':
            print(f"#{r['item_id']} | {r['data']:%d/%m/%Y} | {r['paciente']} | R$ {r['valor']} | {r['status']} | {r['procedimento'][:70]}")

    print()
    print('=== PENDENTES CT ou R$ 350 ===')
    for r in sorted(pendentes + outros_status, key=lambda x: (x['data'], x['paciente'])):
        if r['modalidade'] == 'CT' or r['valor'] == Decimal('350'):
            print(f"#{r['item_id']} | {r['data']:%d/%m/%Y} | {r['paciente']} | {r['modalidade']} | R$ {r['valor']} | {r['status']} | conf={r['conferido']}")

    print()
    print('=== BUSCA VANDERNILSON / IZABEL (qualquer status) ===')
    for fat in fats:
        nome = norm(fat.nome or '')
        if 'VANDERNILSON' in nome or 'IZABEL OLIVEIRA' in nome:
            for item in fat.itens_servico.all():
                print(
                    f"#{item.id} fat #{fat.id} | {fat.data:%d/%m/%Y} | {fat.nome} | "
                    f"{item.modalidade} | R$ {valor_item(item)} | {item.status_conferencia} | conf={item.conferido}"
                )


if __name__ == '__main__':
    main()
