from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render

from categoria.models import Categoria
from empresa.models import Empresa
from fluxo_de_caixa.services.montar_fluxo_mensal import (
    FLAG_PCT_LIMITE,
    cabecalhos_meses,
    montar_dados_completos,
    montar_grafico_planilha,
    montar_linhas_planilha,
)


@login_required
def fluxo_caixa_mensal(request):
    ano = int(request.GET.get('ano', datetime.now().year))
    modo = request.GET.get('modo', 'planilha')
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        from django.contrib import messages
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('dashboard:index')
    empresa = Empresa.objects.get(id=empresa_id)

    meses = list(range(1, 13))
    context = {
        'empresa': empresa,
        'meses': meses,
        'meses_cab': cabecalhos_meses(ano),
        'ano': ano,
        'anos_disponiveis': range(2020, datetime.now().year + 2),
        'flag_pct_limite': float(FLAG_PCT_LIMITE),
        'modo': modo,
    }

    if modo == 'completo':
        dados, grafico_torre = montar_dados_completos(empresa, ano)
        context['dados'] = dados
        context['grafico_torre'] = grafico_torre
    else:
        linhas = montar_linhas_planilha(empresa, ano)
        context['linhas'] = linhas
        context['grafico_planilha'] = montar_grafico_planilha(linhas, ano)
        context['grafico_torre'] = {'tem_dados': False}

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
            'nome_completo': f'{categoria.classificacao} {categoria.nome}'.strip(),
            'tipo': categoria.tipo,
            'tipo_display': tipo_display,
            'grupo': categoria.grupo,
        })

    return JsonResponse({'categorias': categorias_data})
