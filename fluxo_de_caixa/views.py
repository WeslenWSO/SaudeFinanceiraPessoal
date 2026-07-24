from datetime import datetime
from decimal import Decimal
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render

from categoria.models import Categoria
from contasapagar.models import ContasaPagar
from contasareceber.models import BaixaContaAReceber
from empresa.models import Empresa
from notasfiscais.models import NotaFiscalServico
from planejamento_orcamentario.models import LancamentoOrcamento


# Alerta quando |% diferença| >= este valor
FLAG_PCT_LIMITE = Decimal('10')


def _celula_cmp(realizado, planejado, comparar=True):
    """
    Célula mensal: Realizado (fluxo) x Planejado (orçamento).
    % diferença = (realizado − planejado) / planejado × 100
    """
    r = Decimal(str(realizado or 0))
    p = Decimal(str(planejado or 0))
    pct = None
    flag = False
    flag_tipo = ''

    if comparar:
        if p != 0:
            pct = ((r - p) / p * Decimal('100')).quantize(Decimal('0.01'))
            if abs(pct) >= FLAG_PCT_LIMITE:
                flag = True
                flag_tipo = 'acima' if pct > 0 else 'abaixo'
            else:
                flag_tipo = 'ok'
        elif r != 0:
            # Há realizado sem previsto no orçamento
            flag = True
            flag_tipo = 'sem_previsto'

    return {
        'realizado': r,
        'planejado': p,
        'pct': pct,
        'tem_pct': pct is not None,
        'flag': flag,
        'flag_tipo': flag_tipo,
    }


def _celulas_vazias(comparar=False):
    return [_celula_cmp(0, 0, comparar=comparar) for _ in range(12)]


def _mapa_planejado_por_categoria(empresa, ano):
    """categoria_id → lista de 12 Decimal (jan…dez) com soma dos lançamentos orçamentários."""
    mapa = {}
    qs = (
        LancamentoOrcamento.objects.filter(
            empresa=empresa,
            item__ativo=True,
            item__categoria_id__isnull=False,
            data_lancamento__year=ano,
        )
        .values('item__categoria_id', 'data_lancamento__month')
        .annotate(total=Sum('valor'))
    )
    for row in qs:
        cid = row['item__categoria_id']
        mes = row['data_lancamento__month']
        if cid not in mapa:
            mapa[cid] = [Decimal('0')] * 12
        mapa[cid][mes - 1] += row['total'] or Decimal('0')
    return mapa


def _plan_cat(mapa, categoria_id, mes):
    serie = mapa.get(categoria_id)
    if not serie:
        return Decimal('0')
    return serie[mes - 1]


def _plan_soma_categorias(mapa, categorias, mes):
    total = Decimal('0')
    for cat in categorias:
        total += _plan_cat(mapa, cat.id, mes)
    return total


def _linha_tem_movimento(valores):
    return any(
        (c.get('realizado') or 0) != 0 or (c.get('planejado') or 0) != 0
        for c in valores
    )


@login_required
def fluxo_caixa_mensal(request):
    ano = int(request.GET.get('ano', datetime.now().year))
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        from django.contrib import messages
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('dashboard:index')
    empresa = Empresa.objects.get(id=empresa_id)

    categorias_sistema = Categoria.objects.filter(empresa=empresa)
    receita_categorias = list(categorias_sistema.filter(tipo='R'))
    despesa_categorias = list(categorias_sistema.filter(tipo='D'))
    investimento_categorias = list(categorias_sistema.filter(tipo='I'))
    lucro_categorias = list(categorias_sistema.filter(tipo='L'))

    meses = range(1, 13)
    dados = []
    mapa_plan = _mapa_planejado_por_categoria(empresa, ano)

    # ——— FATURAMENTO (sem cruzamento com orçamento por categoria) ———
    faturamento_bruto = {
        'categoria': {'nome': 'FATURAMENTO BRUTO', 'tipo': 'faturamento'},
        'valores': [],
        'subtotal': True,
    }
    faturamento_liquido = {
        'categoria': {'nome': 'FATURAMENTO LÍQUIDO', 'tipo': 'faturamento'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        total_bruto = NotaFiscalServico.objects.filter(
            empresa=empresa, data_emissao__year=ano, data_emissao__month=mes,
        ).aggregate(total=Sum('valor_bruto'))['total'] or 0
        total_liq = NotaFiscalServico.objects.filter(
            empresa=empresa, data_emissao__year=ano, data_emissao__month=mes,
        ).aggregate(total=Sum('valor_liquido'))['total'] or 0
        faturamento_bruto['valores'].append(_celula_cmp(total_bruto, 0, comparar=False))
        faturamento_liquido['valores'].append(_celula_cmp(total_liq, 0, comparar=False))
    if _linha_tem_movimento(faturamento_bruto['valores']):
        dados.append(faturamento_bruto)
    if _linha_tem_movimento(faturamento_liquido['valores']):
        dados.append(faturamento_liquido)

    # ——— RECEITA ———
    receita_total = {
        'categoria': {'nome': 'RECEITA', 'tipo': 'receita'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        realizado = BaixaContaAReceber.objects.filter(
            empresa=empresa,
            conta_a_receber__categoria__tipo='R',
            data_recebimento__year=ano,
            data_recebimento__month=mes,
        ).aggregate(total=Sum('valor_recebido'))['total'] or 0
        planejado = _plan_soma_categorias(mapa_plan, receita_categorias, mes)
        receita_total['valores'].append(_celula_cmp(realizado, planejado))
    if _linha_tem_movimento(receita_total['valores']):
        dados.append(receita_total)

    grupos_receita = {c.grupo for c in receita_categorias}
    for grupo in sorted(grupos_receita, key=lambda g: (g is None, g or '')):
        cats = [c for c in receita_categorias if c.grupo == grupo]
        if grupo:
            dados.append({
                'categoria': {'nome': f'{grupo}', 'tipo': 'grupo'},
                'valores': _celulas_vazias(),
                'subtotal': False,
                'grupo': True,
            })
        for categoria in cats:
            linha = {
                'categoria': {
                    'id': categoria.id,
                    'nome': f'{categoria.classificacao} {categoria.nome}',
                    'tipo': 'receita',
                },
                'valores': [],
            }
            for mes in meses:
                realizado = BaixaContaAReceber.objects.filter(
                    empresa=empresa,
                    conta_a_receber__categoria=categoria,
                    data_recebimento__year=ano,
                    data_recebimento__month=mes,
                ).aggregate(total=Sum('valor_recebido'))['total'] or 0
                planejado = _plan_cat(mapa_plan, categoria.id, mes)
                linha['valores'].append(_celula_cmp(realizado, planejado))
            if _linha_tem_movimento(linha['valores']):
                dados.append(linha)

    # ——— DESPESA ———
    despesa_total = {
        'categoria': {'nome': 'DESPESA', 'tipo': 'despesa'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        realizado = ContasaPagar.objects.filter(
            fornecedor__empresa=empresa,
            categoria__tipo='D',
            dtPag__year=ano,
            dtPag__month=mes,
            valorPago__gt=0,
        ).aggregate(total=Sum('valorPago'))['total'] or 0
        planejado = _plan_soma_categorias(mapa_plan, despesa_categorias, mes)
        despesa_total['valores'].append(_celula_cmp(realizado, planejado))
    dados.append(despesa_total)

    grupos_despesa = {c.grupo for c in despesa_categorias}
    for grupo in sorted(grupos_despesa, key=lambda g: (g is None, g or '')):
        cats = [c for c in despesa_categorias if c.grupo == grupo]
        if grupo:
            dados.append({
                'categoria': {'nome': f'{grupo}', 'tipo': 'grupo'},
                'valores': _celulas_vazias(),
                'subtotal': False,
                'grupo': True,
            })
        for categoria in cats:
            linha = {
                'categoria': {
                    'id': categoria.id,
                    'nome': f'{categoria.classificacao} {categoria.nome}',
                    'tipo': 'despesa',
                },
                'valores': [],
            }
            for mes in meses:
                realizado = ContasaPagar.objects.filter(
                    fornecedor__empresa=empresa,
                    categoria=categoria,
                    dtPag__year=ano,
                    dtPag__month=mes,
                ).aggregate(total=Sum('valorPago'))['total'] or 0
                planejado = _plan_cat(mapa_plan, categoria.id, mes)
                linha['valores'].append(_celula_cmp(realizado, planejado))
            if _linha_tem_movimento(linha['valores']):
                dados.append(linha)

    # ——— RD ———
    rd_linha = {
        'categoria': {'nome': 'RD - Resultado', 'tipo': 'resultado'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        r = receita_total['valores'][mes - 1]
        d = despesa_total['valores'][mes - 1]
        rd_linha['valores'].append(_celula_cmp(
            r['realizado'] - d['realizado'],
            r['planejado'] - d['planejado'],
        ))
    dados.append(rd_linha)

    # ——— INVESTIMENTO ———
    investimento_total = {
        'categoria': {'nome': 'INVESTIMENTO', 'tipo': 'investimento'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        realizado = ContasaPagar.objects.filter(
            fornecedor__empresa=empresa,
            categoria__tipo='I',
            dtPag__year=ano,
            dtPag__month=mes,
            valorPago__gt=0,
        ).aggregate(total=Sum('valorPago'))['total'] or 0
        planejado = _plan_soma_categorias(mapa_plan, investimento_categorias, mes)
        investimento_total['valores'].append(_celula_cmp(realizado, planejado))
    dados.append(investimento_total)

    grupos_investimento = {c.grupo for c in investimento_categorias}
    for grupo in sorted(grupos_investimento, key=lambda g: (g is None, g or '')):
        cats = [c for c in investimento_categorias if c.grupo == grupo]
        if grupo:
            dados.append({
                'categoria': {'nome': f'{grupo}', 'tipo': 'grupo'},
                'valores': _celulas_vazias(),
                'subtotal': False,
                'grupo': True,
            })
        for categoria in cats:
            linha = {
                'categoria': {
                    'id': categoria.id,
                    'nome': f'{categoria.classificacao} {categoria.nome}',
                    'tipo': 'investimento',
                },
                'valores': [],
            }
            for mes in meses:
                realizado = ContasaPagar.objects.filter(
                    fornecedor__empresa=empresa,
                    categoria=categoria,
                    dtPag__year=ano,
                    dtPag__month=mes,
                    valorPago__gt=0,
                ).aggregate(total=Sum('valorPago'))['total'] or 0
                planejado = _plan_cat(mapa_plan, categoria.id, mes)
                linha['valores'].append(_celula_cmp(realizado, planejado))
            if _linha_tem_movimento(linha['valores']):
                dados.append(linha)

    # ——— RI ———
    ri_linha = {
        'categoria': {'nome': 'RI - Resultado', 'tipo': 'resultado'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        rd = rd_linha['valores'][mes - 1]
        inv = investimento_total['valores'][mes - 1]
        ri_linha['valores'].append(_celula_cmp(
            rd['realizado'] - inv['realizado'],
            rd['planejado'] - inv['planejado'],
        ))
    dados.append(ri_linha)

    # ——— DL ———
    dl_total = {
        'categoria': {'nome': 'DL - Distribuição de Lucro', 'tipo': 'lucro'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        realizado = ContasaPagar.objects.filter(
            fornecedor__empresa=empresa,
            categoria__tipo='L',
            dtPag__year=ano,
            dtPag__month=mes,
            valorPago__gt=0,
        ).aggregate(total=Sum('valorPago'))['total'] or 0
        planejado = _plan_soma_categorias(mapa_plan, lucro_categorias, mes)
        dl_total['valores'].append(_celula_cmp(realizado, planejado))
    dados.append(dl_total)

    grupos_lucro = {c.grupo for c in lucro_categorias}
    for grupo in sorted(grupos_lucro, key=lambda g: (g is None, g or '')):
        cats = [c for c in lucro_categorias if c.grupo == grupo]
        if grupo:
            dados.append({
                'categoria': {'nome': f'{grupo}', 'tipo': 'grupo'},
                'valores': _celulas_vazias(),
                'subtotal': False,
                'grupo': True,
            })
        for categoria in cats:
            linha = {
                'categoria': {
                    'id': categoria.id,
                    'nome': f'{categoria.classificacao} {categoria.nome}',
                    'tipo': 'lucro',
                },
                'valores': [],
            }
            for mes in meses:
                realizado = ContasaPagar.objects.filter(
                    fornecedor__empresa=empresa,
                    categoria=categoria,
                    dtPag__year=ano,
                    dtPag__month=mes,
                    valorPago__gt=0,
                ).aggregate(total=Sum('valorPago'))['total'] or 0
                planejado = _plan_cat(mapa_plan, categoria.id, mes)
                linha['valores'].append(_celula_cmp(realizado, planejado))
            if _linha_tem_movimento(linha['valores']):
                dados.append(linha)

    # ——— TOTAL GERAL = RI − DL ———
    total_geral = {
        'categoria': {'nome': 'TOTAL GERAL', 'tipo': 'total'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        ri = ri_linha['valores'][mes - 1]
        dl = dl_total['valores'][mes - 1]
        total_geral['valores'].append(_celula_cmp(
            ri['realizado'] - dl['realizado'],
            ri['planejado'] - dl['planejado'],
        ))
    dados.append(total_geral)

    meses_lbl = (
        'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
        'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
    )
    labels = [f'{meses_lbl[m - 1]}/{ano}' for m in meses]

    def _serie(linha, chave):
        return [float(cel.get(chave) or 0) for cel in linha['valores']]

    receitas_real = _serie(receita_total, 'realizado')
    receitas_plan = _serie(receita_total, 'planejado')
    despesas_real = _serie(despesa_total, 'realizado')
    despesas_plan = _serie(despesa_total, 'planejado')
    resultado_real = _serie(total_geral, 'realizado')
    resultado_plan = _serie(total_geral, 'planejado')

    grafico_torre = {
        'labels_json': json.dumps(labels, ensure_ascii=False),
        'receitas_real_json': json.dumps(receitas_real),
        'receitas_plan_json': json.dumps(receitas_plan),
        'despesas_real_json': json.dumps(despesas_real),
        'despesas_plan_json': json.dumps(despesas_plan),
        'resultado_real_json': json.dumps(resultado_real),
        'resultado_plan_json': json.dumps(resultado_plan),
        'tem_dados': any(
            v != 0
            for serie in (
                receitas_real, receitas_plan,
                despesas_real, despesas_plan,
                resultado_real, resultado_plan,
            )
            for v in serie
        ),
    }

    context = {
        'dados': dados,
        'meses': meses,
        'ano': ano,
        'anos_disponiveis': range(2025, 2041),
        'flag_pct_limite': float(FLAG_PCT_LIMITE),
        'grafico_torre': grafico_torre,
    }
    return render(request, 'fluxo_de_caixa/fluxo_caixa_mensal.html', context)


@login_required
def buscar_categorias(request):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'error': 'Empresa não encontrada na sessão.'}, status=400)

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({'error': 'Empresa não encontrada.'}, status=404)

    termo = request.GET.get('q', '').strip()
    if len(termo) < 4:
        return JsonResponse({'categorias': []})

    categorias = Categoria.objects.filter(
        empresa=empresa
    ).filter(
        Q(nome__icontains=termo) | Q(classificacao__icontains=termo)
    ).order_by('tipo', 'nome')[:20]

    categorias_data = []
    for categoria in categorias:
        tipo_display = {
            'R': 'Receita',
            'D': 'Despesa',
            'I': 'Investimento',
            'L': 'Distribuição de Lucro',
        }.get(categoria.tipo, categoria.tipo)

        categorias_data.append({
            'id': categoria.id,
            'nome': categoria.nome,
            'classificacao': categoria.classificacao,
            'nome_completo': f'{categoria.classificacao} {categoria.nome}',
            'tipo': categoria.tipo,
            'tipo_display': tipo_display,
            'grupo': categoria.grupo,
        })

    return JsonResponse({'categorias': categorias_data})
