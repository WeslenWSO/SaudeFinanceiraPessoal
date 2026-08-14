from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from .forms import AtendenteAcademiaForm, LancamentoAtendenteDiaForm, LancamentoCancelamentosDiaForm
from .models import (
    AtendenteAcademia,
    ItemAtendenteDiario,
    LancamentoVendasDiario,
    PeriodoAcademia,
    calcular_churn_pct,
    garantir_atendentes_padrao,
    obter_periodo_mm_aaaa,
)


MESES_PT = (
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
)


def _parse_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _periodo_mes(request) -> tuple[int, int]:
    hoje = date.today()
    ano = _parse_int(request.GET.get('ano'), hoje.year)
    mes = _parse_int(request.GET.get('mes'), hoje.month)
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


def _empresa_id(request):
    return request.session.get('empresa_id')


def _atendentes_empresa(empresa_id):
    garantir_atendentes_padrao(empresa_id)
    return list(
        AtendenteAcademia.objects.filter(empresa_id=empresa_id, ativo=True).order_by('ordem', 'nome')
    )


def _itens_atendente_map(lancamento):
    if not lancamento or not lancamento.pk:
        return {}
    return {
        item.atendente_id: item
        for item in lancamento.itens_atendente.select_related('atendente').all()
    }


def _salvar_item_atendente(lancamento, atendente, oport, balcao, site, cancel):
    if not lancamento.pk:
        lancamento.save()
    ItemAtendenteDiario.objects.update_or_create(
        lancamento=lancamento,
        atendente=atendente,
        defaults={
            'oport': oport,
            'vendas': balcao,
            'site': site,
            'cancel': cancel,
        },
    )
    lancamento.recalcular_derivados()
    lancamento.save(update_fields=[
        'oport_balcao', 'balcao', 'site', 'total_dia',
        'cancel_inadimplentes', 'cancel_solicitados', 'cancel_negassist',
        'total_cancel_dia', 'churn_dia', 'conversao_balcao_pct', 'saldo_comercial',
    ])


class EmpresaRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not _empresa_id(request):
            messages.error(request, 'Selecione uma empresa.')
            return redirect('empresa:trocar')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = _empresa_id(self.request)
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs


class LancamentoVendasMixin(EmpresaRequiredMixin):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa_id'] = _empresa_id(self.request)
        ano, mes = _periodo_mes(self.request)
        kwargs['ano_ref'] = ano
        kwargs['mes_ref'] = mes
        return kwargs

    def _contexto_atendentes(self, lancamento=None):
        atendentes = _atendentes_empresa(_empresa_id(self.request))
        itens_map = _itens_atendente_map(lancamento)
        linhas = []
        for atendente in atendentes:
            item = itens_map.get(atendente.id)
            linhas.append({
                'atendente': atendente,
                'oport': item.oport if item else 0,
                'vendas': item.vendas if item else 0,
                'site': item.site if item else 0,
                'cancel': item.cancel if item else 0,
            })
        atendente_sel = _parse_int(self.request.GET.get('atendente'))
        resumo_vendas = {
            'oport_balcao': 0,
            'balcao': 0,
            'site': 0,
            'total_dia': 0,
            'conversao_balcao_pct': 0,
        }
        if lancamento and lancamento.pk:
            resumo_vendas = {
                'oport_balcao': lancamento.oport_balcao,
                'balcao': lancamento.balcao,
                'site': lancamento.site,
                'total_dia': lancamento.total_dia,
                'conversao_balcao_pct': lancamento.conversao_balcao_pct,
            }
        atendentes_dados = {
            str(linha['atendente'].id): {
                'oport': linha['oport'],
                'vendas': linha['vendas'],
                'site': linha['site'],
                'cancel': linha['cancel'],
            }
            for linha in linhas
        }
        return {
            'atendentes_linhas': linhas,
            'atendentes': atendentes,
            'atendente_selecionado': atendente_sel,
            'resumo_vendas': resumo_vendas,
            'atendentes_dados': atendentes_dados,
        }

    def _processar_salvamento(self, form, lancamento):
        atendente = form.cleaned_data.get('atendente')
        if not atendente:
            form.add_error('atendente', 'Selecione o atendente.')
            return None

        oport = form.cleaned_data.get('atend_oport') or 0
        balcao = form.cleaned_data.get('atend_balcao') or 0
        site = form.cleaned_data.get('atend_site') or 0
        cancel = form.cleaned_data.get('atend_cancel') or 0

        with transaction.atomic():
            _salvar_item_atendente(lancamento, atendente, oport, balcao, site, cancel)

        messages.success(
            self.request,
            f'Gravado para {atendente.nome}: oport {oport}, vendas {balcao}, site {site}, cancel {cancel}.',
        )
        return lancamento

    def _url_planilha_mes(self, lancamento):
        d = lancamento.data
        return f"{reverse('indicadores:lancamento_vendas_listar')}?ano={d.year}&mes={d.month}"

    def _aplicar_cancelamentos(self, form, lancamento):
        lancamento.cancel_inadimplentes = form.cleaned_data.get('cancel_inadimplentes') or 0
        lancamento.cancel_solicitados = form.cleaned_data.get('cancel_solicitados') or 0
        lancamento.cancel_negassist = form.cleaned_data.get('cancel_negassist') or 0
        lancamento.save()
        messages.success(
            self.request,
            f'Cancelamentos gravados em {lancamento.data:%d/%m/%Y}: total {lancamento.total_cancel_dia}.',
        )
        return lancamento


class LancamentoVendasList(LancamentoVendasMixin, ListView):
    model = LancamentoVendasDiario
    template_name = 'indicadores/lancamento_vendas_listar.html'
    context_object_name = 'lancamentos'

    def get_queryset(self):
        ano, mes = _periodo_mes(self.request)
        return (
            super()
            .get_queryset()
            .filter(data__year=ano, data__month=mes)
            .prefetch_related('itens_atendente__atendente')
            .order_by('data')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ano, mes = _periodo_mes(self.request)
        empresa_id = _empresa_id(self.request)
        atendentes = _atendentes_empresa(empresa_id)
        totais = context['lancamentos'].aggregate(
            oport_balcao=Sum('oport_balcao'),
            balcao=Sum('balcao'),
            site=Sum('site'),
            total_dia=Sum('total_dia'),
            cancel_inadimplentes=Sum('cancel_inadimplentes'),
            cancel_solicitados=Sum('cancel_solicitados'),
            cancel_negassist=Sum('cancel_negassist'),
            total_cancel_dia=Sum('total_cancel_dia'),
            saldo_comercial=Sum('saldo_comercial'),
        )
        totais_atendentes = {}
        for atendente in atendentes:
            agg = ItemAtendenteDiario.objects.filter(
                lancamento__empresa_id=empresa_id,
                lancamento__data__year=ano,
                lancamento__data__month=mes,
                atendente=atendente,
            ).aggregate(
                oport=Sum('oport'),
                vendas=Sum('vendas'),
                site=Sum('site'),
                cancel=Sum('cancel'),
            )
            totais_atendentes[atendente.id] = agg

        periodo = obter_periodo_mm_aaaa(empresa_id, ano, mes)
        qt_ativos_mes = (periodo.qt_ativos or 0) if periodo else 0
        churn_mes = periodo.churn_pct if periodo else Decimal('0.0000')

        linhas = []
        for lanc in context['lancamentos']:
            mapa = {i.atendente_id: i for i in lanc.itens_atendente.all()}
            linhas.append({
                'lanc': lanc,
                'atend_itens': [mapa.get(a.id) for a in atendentes],
                'churn_dia': calcular_churn_pct(qt_ativos_mes, lanc.total_cancel_dia),
            })

        ano_ant, mes_ant = _mes_vizinho(ano, mes, -1)
        ano_prox, mes_prox = _mes_vizinho(ano, mes, 1)
        context.update({
            'descricao': 'Lançamento diário — academia',
            'now': timezone.now(),
            'ano': ano,
            'mes': mes,
            'mes_label': f'{MESES_PT[mes]}/{ano}',
            'periodo': periodo,
            'qt_ativos_mes': qt_ativos_mes,
            'churn_mes': churn_mes,
            'churn_mes_fmt': churn_mes.quantize(Decimal('0.01')),
            'totais': totais,
            'atendentes': atendentes,
            'linhas': linhas,
            'totais_atend_list': [totais_atendentes.get(a.id, {}) for a in atendentes],
            'url_mes_anterior': f'?ano={ano_ant}&mes={mes_ant}',
            'url_mes_proximo': f'?ano={ano_prox}&mes={mes_prox}',
        })
        return context


class LancamentoVendasCreate(LancamentoVendasMixin, CreateView):
    model = LancamentoVendasDiario
    form_class = LancamentoAtendenteDiaForm
    template_name = 'indicadores/lancamento_vendas_form.html'

    def get_initial(self):
        initial = super().get_initial()
        ano, mes = _periodo_mes(self.request)
        dia = _parse_int(self.request.GET.get('dia'), 1)
        dia = max(1, min(dia, monthrange(ano, mes)[1]))
        initial['data'] = date(ano, mes, dia)
        atendente_id = _parse_int(self.request.GET.get('atendente'))
        if atendente_id:
            initial['atendente'] = atendente_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Lançar dia — academia'
        context['modo'] = 'criar'
        context.update(self._contexto_atendentes())
        return context

    def form_valid(self, form):
        empresa_id = _empresa_id(self.request)
        data = form.cleaned_data['data']
        existente = LancamentoVendasDiario.objects.filter(empresa_id=empresa_id, data=data).first()
        if existente:
            if self._processar_salvamento(form, existente) is None:
                return self.form_invalid(form)
            return redirect(self._url_planilha_mes(existente))

        lancamento = LancamentoVendasDiario.objects.create(
            empresa_id=empresa_id,
            data=data,
        )
        if self._processar_salvamento(form, lancamento) is None:
            lancamento.delete()
            return self.form_invalid(form)

        return redirect(self._url_planilha_mes(lancamento))


class LancamentoVendasUpdate(LancamentoVendasMixin, UpdateView):
    model = LancamentoVendasDiario
    form_class = LancamentoAtendenteDiaForm
    template_name = 'indicadores/lancamento_vendas_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object:
            kwargs['ano_ref'] = self.object.data.year
            kwargs['mes_ref'] = self.object.data.month
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object:
            form.fields['data'].disabled = True
        return form

    def get_initial(self):
        initial = super().get_initial()
        atendente_id = _parse_int(self.request.GET.get('atendente'))
        if atendente_id and self.object:
            item = self.object.itens_atendente.filter(atendente_id=atendente_id).first()
            if item:
                initial.update({
                    'atendente': atendente_id,
                    'atend_oport': item.oport,
                    'atend_balcao': item.vendas,
                    'atend_site': item.site,
                    'atend_cancel': item.cancel,
                })
            else:
                initial['atendente'] = atendente_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = f'Lançamento — {self.object.data:%d/%m/%Y}'
        context['modo'] = 'editar'
        context['lancamento'] = self.object
        context.update(self._contexto_atendentes(self.object))
        return context

    def form_valid(self, form):
        if self._processar_salvamento(form, self.object) is None:
            return self.form_invalid(form)
        return redirect(self._url_planilha_mes(self.object))


class LancamentoCancelamentosCreate(LancamentoVendasMixin, CreateView):
    model = LancamentoVendasDiario
    form_class = LancamentoCancelamentosDiaForm
    template_name = 'indicadores/lancamento_cancelamentos_form.html'

    def get_initial(self):
        initial = super().get_initial()
        ano, mes = _periodo_mes(self.request)
        dia = _parse_int(self.request.GET.get('dia'), 1)
        dia = max(1, min(dia, monthrange(ano, mes)[1]))
        initial['data'] = date(ano, mes, dia)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Lançar cancelamentos — academia'
        context['modo'] = 'criar'
        ano, mes = _periodo_mes(self.request)
        context['ano'] = ano
        context['mes'] = mes
        return context

    def form_valid(self, form):
        empresa_id = _empresa_id(self.request)
        data = form.cleaned_data['data']
        lancamento = LancamentoVendasDiario.objects.filter(empresa_id=empresa_id, data=data).first()
        if not lancamento:
            lancamento = LancamentoVendasDiario(empresa_id=empresa_id, data=data)
        self._aplicar_cancelamentos(form, lancamento)
        return redirect(self._url_planilha_mes(lancamento))


class LancamentoCancelamentosUpdate(LancamentoVendasMixin, UpdateView):
    model = LancamentoVendasDiario
    form_class = LancamentoCancelamentosDiaForm
    template_name = 'indicadores/lancamento_cancelamentos_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object:
            kwargs['ano_ref'] = self.object.data.year
            kwargs['mes_ref'] = self.object.data.month
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object:
            form.fields['data'].disabled = True
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = f'Cancelamentos — {self.object.data:%d/%m/%Y}'
        context['modo'] = 'editar'
        context['lancamento'] = self.object
        return context

    def form_valid(self, form):
        self._aplicar_cancelamentos(form, self.object)
        return redirect(self._url_planilha_mes(self.object))


class LancamentoVendasDelete(LancamentoVendasMixin, DeleteView):
    model = LancamentoVendasDiario

    def get_success_url(self):
        d = self.object.data
        return f"{reverse('indicadores:lancamento_vendas_listar')}?ano={d.year}&mes={d.month}"

    def form_valid(self, form):
        messages.success(self.request, 'Lançamento excluído.')
        return super().form_valid(form)


class AtendenteList(EmpresaRequiredMixin, ListView):
    model = AtendenteAcademia
    template_name = 'indicadores/atendente_listar.html'

    def dispatch(self, request, *args, **kwargs):
        empresa_id = _empresa_id(request)
        if empresa_id:
            garantir_atendentes_padrao(empresa_id)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().order_by('ordem', 'nome')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Atendentes (academia)'
        return context


class AtendenteCreate(EmpresaRequiredMixin, CreateView):
    model = AtendenteAcademia
    form_class = AtendenteAcademiaForm
    template_name = 'indicadores/atendente_form.html'
    success_url = reverse_lazy('indicadores:atendente_listar')

    def form_valid(self, form):
        form.instance.empresa_id = _empresa_id(self.request)
        messages.success(self.request, 'Atendente criado.')
        return super().form_valid(form)


class AtendenteUpdate(EmpresaRequiredMixin, UpdateView):
    model = AtendenteAcademia
    form_class = AtendenteAcademiaForm
    template_name = 'indicadores/atendente_form.html'
    success_url = reverse_lazy('indicadores:atendente_listar')

    def form_valid(self, form):
        messages.success(self.request, 'Atendente atualizado.')
        return super().form_valid(form)
