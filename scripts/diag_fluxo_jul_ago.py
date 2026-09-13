"""Diagnóstico fluxo SF vs CA — jul/ago 2026."""
import os, sys
from datetime import date
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from django.db.models import Q, Sum
from contasapagar.models import ContasaPagar
from empresa.models import Empresa
from fluxo_de_caixa.services.montar_fluxo_mensal import (
    montar_linhas_planilha, _mapa_despesas_por_categoria_mes,
)
from dashboard.conta_azul.client import ContaAzulClient
from dashboard.conta_azul.sync import _item_financeiro_pago, _total_pago_liquido_item

empresa = Empresa.objects.get(pk=16)
ano = 2026
linhas = montar_linhas_planilha(empresa, ano)

def linha(cat, mes):
    idx = mes - 1
    for l in linhas:
        if l.get('categoria') == cat and l.get('nivel') == 'subtotal':
            return l['valores'][idx]
    return Decimal('0')

for mes in (7, 8):
    print('=' * 60, f'MES {mes}')
    desp = linha('DESPESAS', mes)
    inv = linha('INVESTIMENTO', mes)
    dl = linha('DISTRIBUIÇÃO DE LUCRO', mes)
    print(f'FLUXO SF: desp={desp} inv={inv} dl={dl} TOTAL={desp+inv+dl}')

    # CAP pagas only
    pagas = ContasaPagar.objects.filter(
        empresa_id=16, conta_azul_parcela_id__gt='', status='pago',
        dtPag__year=ano, dtPag__month=mes, valorPago__gt=0,
    ).aggregate(t=Sum('valorPago'))['t'] or 0
    print(f'CAP pagas sync: {pagas}')

    # unpaid in fluxo map (vencimento)
    for tipo, label in [('D', 'desp'), ('I', 'inv'), ('L', 'lucro')]:
        mapa = _mapa_despesas_por_categoria_mes(empresa, ano, tipo)
        paid = Decimal('0')
        unpaid = Decimal('0')
        base = ContasaPagar.objects.filter(empresa_id=16, conta_azul_parcela_id__gt='', categoria__tipo=tipo)
        for row in base.filter(dtPag__year=ano, dtPag__month=mes, valorPago__gt=0).values('categoria_id').annotate(t=Sum('valorPago')):
            paid += row['t'] or 0
        for row in base.filter(dtvenc__year=ano, dtvenc__month=mes).filter(Q(valorPago__isnull=True)|Q(valorPago=0)).values('categoria_id').annotate(t=Sum('valorDoc')):
            unpaid += row['t'] or 0
        print(f'  tipo {label}: pagas={paid} em_aberto_venc={unpaid} mapa_soma={sum(v for (c,m),v in mapa.items() if m==mes)}')

    de = date(ano, mes, 1)
    ate = date(ano, mes, 31 if mes in (1,3,5,7,8,10,12) else 30)
    client = ContaAzulClient.para_empresa(empresa)
    ca = Decimal('0')
    for it in client.buscar_despesas(pagina=1, tamanho_pagina=100,
        data_pagamento_de=de.isoformat(), data_pagamento_ate=ate.isoformat(),
        data_vencimento_de='2020-01-01', data_vencimento_ate='2027-12-31'):
        pid = str(it.get('id') or '').strip()
        if pid and _item_financeiro_pago(it):
            ca += _total_pago_liquido_item(it)
    print(f'CA API pagas: {ca}')
