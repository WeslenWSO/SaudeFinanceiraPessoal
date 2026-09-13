"""Detalhe das diferenças CA vs SF — jul/ago 2026."""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from contasapagar.models import ContasaPagar  # noqa: E402
from dashboard.conta_azul.client import ContaAzulClient  # noqa: E402
from dashboard.conta_azul.sync import _item_financeiro_pago, _total_pago_liquido_item  # noqa: E402
from empresa.models import Empresa  # noqa: E402

EMPRESA_ID = 16
ANO = 2026


def ultimo_dia(ano: int, mes: int) -> date:
    if mes == 12:
        return date(ano, 12, 31)
    return date(ano, mes + 1, 1).fromordinal(date(ano, mes + 1, 1).toordinal() - 1)


def ca_map(client, de, ate):
    params = {
        'pagina': 1,
        'tamanho_pagina': 100,
        'data_pagamento_de': de.isoformat(),
        'data_pagamento_ate': ate.isoformat(),
        'data_vencimento_de': date(2020, 1, 1).isoformat(),
        'data_vencimento_ate': date(2027, 12, 31).isoformat(),
    }
    mapa = {}
    for it in client.buscar_despesas(**params):
        pid = str(it.get('id') or it.get('id_parcela') or '').strip()
        if pid and _item_financeiro_pago(it):
            mapa[pid] = _total_pago_liquido_item(it)
    return mapa


def main():
    empresa = Empresa.objects.get(pk=EMPRESA_ID)
    client = ContaAzulClient.para_empresa(empresa)

    for mes in (7, 8):
        de = date(ANO, mes, 1)
        ate = ultimo_dia(ANO, mes)
        ca = ca_map(client, de, ate)
        sf_qs = ContasaPagar.objects.filter(
            empresa_id=EMPRESA_ID,
            conta_azul_parcela_id__gt='',
            status='pago',
            dtPag__year=ANO,
            dtPag__month=mes,
            valorPago__gt=0,
        ).select_related('categoria')
        sf = {c.conta_azul_parcela_id: c for c in sf_qs}

        so_sf = set(sf) - set(ca)
        print('=' * 70)
        print(f'Mes {mes}: {len(so_sf)} titulos pagos no SF mas nao no CA (pagamento em {mes})')
        for pid in so_sf:
            c = sf[pid]
            print(f'  R$ {c.valorPago:,.2f} dtPag={c.dtPag} venc={c.dtvenc}')
            print(f'    {c.descricao[:70]}')
            print(f'    cat: {c.categoria.nome if c.categoria_id else "?"} tipo={c.categoria.tipo if c.categoria_id else "?"}')
            # buscar parcela no CA
            try:
                det = client.buscar_parcela_por_id(pid)
                st = det.get('status') or det.get('status_traduzido')
                dp = det.get('data_pagamento') or det.get('data_baixa')
                print(f'    CA parcela: status={st} data_pag={dp} total={det.get("total")}')
            except Exception as e:
                print(f'    CA parcela erro: {e}')


if __name__ == '__main__':
    main()
