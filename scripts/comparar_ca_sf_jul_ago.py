"""Compara Conta Azul (API) vs SF local — julho e agosto."""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from django.db.models import Sum  # noqa: E402

from contasapagar.models import ContasaPagar  # noqa: E402
from contasareceber.models import ContaAReceber  # noqa: E402
from dashboard.conta_azul.client import ContaAzulClient  # noqa: E402
from dashboard.conta_azul.sync import (  # noqa: E402
    _item_financeiro_pago,
    _map_status_receita,
    _total_pago_liquido_item,
    _valor_pago_item,
)
from empresa.models import Empresa  # noqa: E402
from fluxo_de_caixa.services.montar_fluxo_mensal import (  # noqa: E402
    _bloco_emprestimos_planilha,
    _mapa_despesas_por_categoria_mes,
    montar_linhas_planilha,
)

EMPRESA_ID = 16
ANO = 2026


def ultimo_dia(ano: int, mes: int) -> date:
    if mes == 12:
        return date(ano, 12, 31)
    return date(ano, mes + 1, 1).fromordinal(date(ano, mes + 1, 1).toordinal() - 1)


def ca_despesas_pagas(client, de: date, ate: date) -> tuple[Decimal, dict]:
    params = {
        'pagina': 1,
        'tamanho_pagina': 100,
        'data_pagamento_de': de.isoformat(),
        'data_pagamento_ate': ate.isoformat(),
        'data_vencimento_de': date(2020, 1, 1).isoformat(),
        'data_vencimento_ate': date(2027, 12, 31).isoformat(),
    }
    itens = client.buscar_despesas(**params)
    mapa: dict[str, dict] = {}
    total = Decimal('0')
    for it in itens:
        pid = str(it.get('id') or it.get('id_parcela') or '').strip()
        if not pid or not _item_financeiro_pago(it):
            continue
        v = _total_pago_liquido_item(it)
        if v <= 0:
            continue
        mapa[pid] = {'valor': v, 'desc': (it.get('descricao') or '')[:70]}
        total += v
    return total, mapa


def ca_receitas_recebidas(client, de: date, ate: date) -> tuple[Decimal, dict]:
    params = {
        'pagina': 1,
        'tamanho_pagina': 100,
        'data_pagamento_de': de.isoformat(),
        'data_pagamento_ate': ate.isoformat(),
        'data_vencimento_de': date(2020, 1, 1).isoformat(),
        'data_vencimento_ate': date(2027, 12, 31).isoformat(),
    }
    itens = client.buscar_receitas(**params)
    mapa: dict[str, dict] = {}
    total = Decimal('0')
    for it in itens:
        pid = str(it.get('id') or it.get('id_parcela') or '').strip()
        if not pid or _map_status_receita(it) != 'pago':
            continue
        v = _valor_pago_item(it)
        if v <= 0:
            continue
        mapa[pid] = {'valor': v, 'desc': (it.get('descricao') or '')[:70]}
        total += v
    return total, mapa


def sf_cap_pagas(mes: int) -> tuple[Decimal, dict]:
    qs = ContasaPagar.objects.filter(
        empresa_id=EMPRESA_ID,
        conta_azul_parcela_id__gt='',
        status='pago',
        dtPag__year=ANO,
        dtPag__month=mes,
        valorPago__gt=0,
    )
    mapa = {
        c.conta_azul_parcela_id: {'valor': c.valorPago, 'desc': (c.descricao or '')[:70]}
        for c in qs
    }
    total = qs.aggregate(t=Sum('valorPago'))['t'] or Decimal('0')
    return total, mapa


def sf_cap_pendentes_venc(mes: int) -> Decimal:
    return (
        ContasaPagar.objects.filter(
            empresa_id=EMPRESA_ID,
            conta_azul_parcela_id__gt='',
            dtvenc__year=ANO,
            dtvenc__month=mes,
        )
        .filter(status='pendente')
        .aggregate(t=Sum('valorDoc'))['t']
        or Decimal('0')
    )


def sf_car_recebidas(mes: int) -> tuple[Decimal, dict]:
    qs = ContaAReceber.objects.filter(
        empresa_id=EMPRESA_ID,
        conta_azul_parcela_id__gt='',
        status='pago',
        data_recebimento__year=ANO,
        data_recebimento__month=mes,
    )
    mapa = {
        c.conta_azul_parcela_id: {'valor': c.valor_recebido, 'desc': (c.cliente or '')[:70]}
        for c in qs
    }
    total = qs.aggregate(t=Sum('valor_recebido'))['t'] or Decimal('0')
    return total, mapa


def sf_fluxo(empresa, mes: int) -> dict:
    idx = mes - 1
    linhas = montar_linhas_planilha(empresa, ANO)

    def val(cat: str) -> Decimal:
        for lin in linhas:
            if lin.get('categoria') == cat and lin.get('nivel') in ('subtotal', 'total', 'resultado'):
                return lin['valores'][idx]
        return Decimal('0')

    _, emp = _bloco_emprestimos_planilha(empresa, ANO)
    res = val('RESULTADO (Receita − Despesas − Investimento − Distribuição de Lucro)')
    return {
        'receita': val('RECEITA'),
        'despesas': val('DESPESAS'),
        'investimento': val('INVESTIMENTO'),
        'dist_lucro': val('DISTRIBUIÇÃO DE LUCRO'),
        'resultado_pos_dl': res,
        'emprestimos': emp[idx],
        'resultado_geral': res - emp[idx],
    }


def soma_mapa(mapa: dict) -> Decimal:
    return sum(x['valor'] for x in mapa.values())


def diff_mapas(ca: dict, sf: dict, titulo: str) -> None:
    ca_ids = set(ca.keys())
    sf_ids = set(sf.keys())
    so_ca = ca_ids - sf_ids
    so_sf = sf_ids - ca_ids
    dif_val = []
    for pid in ca_ids & sf_ids:
        dv = ca[pid]['valor'] - sf[pid]['valor']
        if abs(dv) > Decimal('0.01'):
            dif_val.append((pid, ca[pid], sf[pid], dv))

    tot_ca = soma_mapa(ca)
    tot_sf = soma_mapa(sf)
    print(f'  {titulo}')
    print(f'    CA API:  R$ {tot_ca:,.2f}  ({len(ca)} titulos)')
    print(f'    SF local: R$ {tot_sf:,.2f}  ({len(sf)} titulos)')
    print(f'    Diferenca: R$ {tot_ca - tot_sf:,.2f}')
    print(f'    So no CA: {len(so_ca)} titulos = R$ {sum(ca[i]["valor"] for i in so_ca):,.2f}')
    print(f'    So no SF: {len(so_sf)} titulos = R$ {sum(sf[i]["valor"] for i in so_sf):,.2f}')
    print(f'    Valor dif (mesmo id): {len(dif_val)} = R$ {sum(d[3] for d in dif_val):,.2f}')
    for pid, c, s, dv in sorted(dif_val, key=lambda x: abs(x[3]), reverse=True)[:8]:
        print(f'      R$ {dv:,.2f} | CA {c["valor"]} SF {s["valor"]} | {c["desc"]}')
    for pid in sorted(so_ca, key=lambda i: ca[i]['valor'], reverse=True)[:5]:
        print(f'      +CA R$ {ca[pid]["valor"]:,.2f} | {ca[pid]["desc"]}')
    for pid in sorted(so_sf, key=lambda i: sf[i]['valor'], reverse=True)[:5]:
        print(f'      +SF R$ {sf[pid]["valor"]:,.2f} | {sf[pid]["desc"]}')


def soma_mapa_tipo(mapa: dict, mes: int) -> Decimal:
    return sum(v for (cid, m), v in mapa.items() if m == mes)


def main() -> None:
    empresa = Empresa.objects.get(pk=EMPRESA_ID)
    client = ContaAzulClient.para_empresa(empresa)
    map_d = _mapa_despesas_por_categoria_mes(empresa, ANO, 'D')
    map_i = _mapa_despesas_por_categoria_mes(empresa, ANO, 'I')
    map_l = _mapa_despesas_por_categoria_mes(empresa, ANO, 'L')

    for mes, nome in ((7, 'Julho'), (8, 'Agosto')):
        de = date(ANO, mes, 1)
        ate = ultimo_dia(ANO, mes)
        print('=' * 70)
        print(f'{nome}/{ANO}  ({de:%d/%m/%Y} a {ate:%d/%m/%Y})')
        print('-' * 70)

        ca_d, map_ca_d = ca_despesas_pagas(client, de, ate)
        sf_d, map_sf_d = sf_cap_pagas(mes)
        ca_r, map_ca_r = ca_receitas_recebidas(client, de, ate)
        sf_r, map_sf_r = sf_car_recebidas(mes)
        fluxo = sf_fluxo(empresa, mes)

        print('DESPESAS (contas a pagar — pagas no mes):')
        diff_mapas(map_ca_d, map_sf_d, 'CAP')

        print('RECEITAS (contas a receber — recebidas no mes):')
        diff_mapas(map_ca_r, map_sf_r, 'CAR')

        desp_fluxo = soma_mapa_tipo(map_d, mes)
        inv_fluxo = soma_mapa_tipo(map_i, mes)
        lucro_fluxo = soma_mapa_tipo(map_l, mes)
        pend_venc = sf_cap_pendentes_venc(mes)

        print('FLUXO DE CAIXA SF (tela):')
        print(f'    Receita:        R$ {fluxo["receita"]:,.2f}')
        print(f'    Despesas:       R$ {fluxo["despesas"]:,.2f}')
        print(f'    Investimento:   R$ {fluxo["investimento"]:,.2f}')
        print(f'    Dist. lucro:    R$ {fluxo["dist_lucro"]:,.2f}')
        print(f'    Emprestimos:    R$ {fluxo["emprestimos"]:,.2f}')
        print(f'    Resultado geral:R$ {fluxo["resultado_geral"]:,.2f}')
        print(f'  Mapa fluxo (incl. em aberto por vencimento):')
        print(f'    Desp+Inv+Lucro: R$ {desp_fluxo + inv_fluxo + lucro_fluxo:,.2f}')
        print(f'    Pendentes venc: R$ {pend_venc:,.2f} (extras no fluxo se em aberto)')
        print(f'  CA API despesas pagas (todas categorias): R$ {ca_d:,.2f}')
        print(f'  SF CAP pagas (todas categorias):          R$ {sf_d:,.2f}')
        print()


if __name__ == '__main__':
    main()
