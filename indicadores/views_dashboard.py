from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import DadosPeriodoAcademiaForm
from .models import (
    Indicador,
    ItemPeriodoAcademia,
    PeriodoAcademia,
    garantir_indicadores_padrao,
)
from .services.calculos import FAIXAS_PREMIACAO_CHURN_LABELS, montar_linha_indicador, premiacao_churn_faixas


MESES_PT = (
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
)


def _empresa_id(request):
    return request.session.get('empresa_id')


def _parse_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _parse_decimal(val):
    bruto = (val or '').strip().replace(',', '.')
    if not bruto:
        return None
    try:
        return Decimal(bruto)
    except InvalidOperation:
        return None


def _parse_date(val):
    if not val:
        return None
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _periodo_mes(request) -> tuple[int, int]:
    hoje = date.today()
    ano = _parse_int(request.GET.get('ano') or request.POST.get('ano'), hoje.year)
    mes = _parse_int(request.GET.get('mes') or request.POST.get('mes'), hoje.month)
    if mes < 1 or mes > 12:
        mes = hoje.month
    if ano < 2000 or ano > 2100:
        ano = hoje.year
    return ano, mes


def _mes_vizinho(ano: int, mes: int, delta: int) -> tuple[int, int]:
    mes += delta
    while mes > 12:
        mes -= 12
        ano += 1
    while mes < 1:
        mes += 12
        ano -= 1
    return ano, mes


def _ultimo_dia_mes(ano: int, mes: int) -> date:
    return date(ano, mes, monthrange(ano, mes)[1])


def _itens_por_indicador(periodo):
    return {
        item.indicador_id: item
        for item in periodo.itens.select_related('indicador').all()
    }


def _garantir_itens_periodo(periodo, indicadores):
    existentes = _itens_por_indicador(periodo)
    criar = []
    for ind in indicadores:
        if ind.id not in existentes:
            criar.append(ItemPeriodoAcademia(periodo=periodo, indicador=ind))
    if criar:
        ItemPeriodoAcademia.objects.bulk_create(criar, ignore_conflicts=True)


def _atualizar_item_churn(periodo, indicadores):
    """Grava churn calculado e valor da premiação no indicador CHURN."""
    churn_ind = next((i for i in indicadores if i.eh_churn), None)
    if not churn_ind:
        return
    item, _ = ItemPeriodoAcademia.objects.get_or_create(
        periodo=periodo,
        indicador=churn_ind,
    )
    item.resultado = periodo.churn_pct
    item.save(update_fields=['resultado'])


def _montar_bloco_area(area_codigo, area_rotulo, indicadores, itens_map, churn_pct):
    linhas = []
    total_premiacao = Decimal('0.00')
    total_receber = Decimal('0.00')
    for ind in indicadores:
        item = itens_map.get(ind.id)
        linha = montar_linha_indicador(ind, item, churn_pct=churn_pct)
        linhas.append(linha)
        total_premiacao += ind.premiacao or Decimal('0')
        total_receber += linha['valor_premiacao']
    alcance = None
    if total_premiacao > 0:
        alcance = (total_receber / total_premiacao * Decimal('100')).quantize(Decimal('0.01'))
    return {
        'codigo': area_codigo,
        'rotulo': area_rotulo,
        'linhas': linhas,
        'total_premiacao': total_premiacao,
        'total_receber': total_receber,
        'alcance_meta_pct': alcance,
    }


def dashboard_academia(request):
    empresa_id = _empresa_id(request)
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:trocar')

    garantir_indicadores_padrao(empresa_id)
    ano, mes = _periodo_mes(request)
    periodo, _ = PeriodoAcademia.objects.get_or_create(
        empresa_id=empresa_id,
        ano=ano,
        mes=mes,
        defaults={
            'data_referencia': _ultimo_dia_mes(ano, mes),
        },
    )

    indicadores = list(
        Indicador.objects.filter(empresa_id=empresa_id, ativo=True).order_by('area', 'ordem', 'nome')
    )
    _garantir_itens_periodo(periodo, indicadores)

    if request.method == 'POST':
        acao = (request.POST.get('acao') or '').strip()
        if acao == 'dados':
            form_post = DadosPeriodoAcademiaForm(request.POST)
            if form_post.is_valid():
                data_ref = form_post.cleaned_data.get('data_referencia')
                ano_m = data_ref.year if data_ref else ano
                mes_m = data_ref.month if data_ref else mes
                periodo_salvar, _ = PeriodoAcademia.objects.get_or_create(
                    empresa_id=empresa_id,
                    ano=ano_m,
                    mes=mes_m,
                    defaults={
                        'data_referencia': data_ref or _ultimo_dia_mes(ano_m, mes_m),
                    },
                )
                form = DadosPeriodoAcademiaForm(request.POST, instance=periodo_salvar)
                if form.is_valid():
                    periodo = form.save()
                    _garantir_itens_periodo(periodo, indicadores)
                    _atualizar_item_churn(periodo, indicadores)
                    valor_churn = premiacao_churn_faixas(periodo.churn_pct)
                    messages.success(
                        request,
                        f'Dados salvos ({mes_m:02d}/{ano_m}). Churn {periodo.churn_pct.quantize(Decimal("0.01"))}% '
                        f'→ premiação CHURN R$ {valor_churn:.2f}.',
                    )
                    ano, mes = ano_m, mes_m
                else:
                    messages.error(request, 'Verifique os dados informados.')
            else:
                messages.error(request, 'Verifique os dados informados.')
        elif acao == 'metas_resultados':
            itens_map = _itens_por_indicador(periodo)
            with transaction.atomic():
                for ind in indicadores:
                    meta = _parse_decimal(request.POST.get(f'meta_{ind.id}'))
                    resultado = _parse_decimal(request.POST.get(f'resultado_{ind.id}'))
                    item = itens_map.get(ind.id)
                    if not item:
                        item = ItemPeriodoAcademia.objects.create(periodo=periodo, indicador=ind)
                    item.meta = meta
                    if ind.eh_churn:
                        item.resultado = periodo.churn_pct
                    else:
                        item.resultado = resultado
                    item.save()
            messages.success(request, 'Metas e resultados salvos.')
        return redirect(f'{reverse("indicadores:dashboard_academia")}?ano={ano}&mes={mes}')

    form_dados = DadosPeriodoAcademiaForm(instance=periodo)
    itens_map = _itens_por_indicador(periodo)
    blocos = []
    for area_codigo, area_rotulo in Indicador.AREA_CHOICES:
        inds_area = [i for i in indicadores if i.area == area_codigo]
        if not inds_area:
            continue
        blocos.append(
            _montar_bloco_area(area_codigo, area_rotulo, inds_area, itens_map, periodo.churn_pct)
        )

    ano_ant, mes_ant = _mes_vizinho(ano, mes, -1)
    ano_prox, mes_prox = _mes_vizinho(ano, mes, 1)

    context = {
        'descricao': 'Dashboard de Academia',
        'ano': ano,
        'mes': mes,
        'mes_label': f'{MESES_PT[mes]}/{ano}',
        'periodo': periodo,
        'form_dados': form_dados,
        'blocos': blocos,
        'churn_pct': periodo.churn_pct,
        'churn_pct_fmt': periodo.churn_pct.quantize(Decimal('0.01')),
        'url_mes_anterior': f'?ano={ano_ant}&mes={mes_ant}',
        'url_mes_proximo': f'?ano={ano_prox}&mes={mes_prox}',
        'faixas_churn': FAIXAS_PREMIACAO_CHURN_LABELS,
    }
    return render(request, 'indicadores/dashboard_academia.html', context)
