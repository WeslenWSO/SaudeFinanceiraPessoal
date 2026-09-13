import decimal
from multiprocessing import context
from typing import Any
from django.db.models.query import QuerySet
from django.http import QueryDict
from django.urls import reverse, reverse_lazy
from django.utils.http import urlencode
from django.utils import timezone
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView
from django.contrib import messages
from django.views.generic.edit import CreateView
from django.views import View
import json
from requests import request
from regrarateio.models import LancamentoRateio, RegraRateio, RegraRateioItem
from regrarateio.services import (
    _regra_usa_valor_manual,
    gerar_rateio_contas_pagar,
    gerar_rateio_contas_receber,
    query_contas_pagar_rateio_candidatas,
    query_contas_receber_rateio_candidatas,
    reaplicar_regra_no_titulo,
    remover_rateio_do_titulo,
    valor_base_titulo_de_lancamento,
    preview_linhas_rateio_por_regra,
)
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.dateparse import parse_date
from decimal import Decimal

from django.db.models import Count, Min, Q, Sum
from django.db.models.functions import Coalesce
from socio.models import Socio
from .forms import FormRecalcularRateioGrupo, FormRegraItem, FormRegraRateio


class RegraCreate(CreateView):
    model = RegraRateio
    form_class = FormRegraRateio
    template_name = 'regra-add-alterar.html'

    success_url = reverse_lazy('regrarateio:regraList')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Adicionar Regra Rateio'
        context['titulo'] = 'Regra Rateio'

        return context

    def form_valid(self, form):
        eid = self.request.session.get('empresa_id')
        if not eid:
            messages.error(self.request, 'Selecione uma empresa para cadastrar a regra de rateio.')
            return self.form_invalid(form)
        form.instance.empresa_id = eid
        messages.success(self.request, 'Regra de rateio criada com sucesso.')
        return super().form_valid(form)  

class RegraICreate(CreateView):
    model = RegraRateioItem
    form_class = FormRegraItem
    template_name= "regraI-add-alterar.html"


    #fields = ['title','description','completed']
    success_url = reverse_lazy('regrarateio:regraList')

    def get_initial(self):
        initial = super().get_initial()
        regra_id = self.request.GET.get('regra')
        if regra_id:
            initial['regrarateio'] = regra_id
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Obter empresa da sessão
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            from empresa.models import Empresa
            kwargs['empresa'] = Empresa.objects.get(id=empresa_id)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Item de Rateio'
        context["titulo"] = 'Item de Rateio'

        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        print(f"Salvando item: {form.cleaned_data}")  # Debug
        response = super().form_valid(form)
        print(f"Item salvo com ID: {self.object.id}")  # Debug
        messages.success(self.request, "Item de rateio criado com sucesso.")
        return redirect('regrarateio:regraList')

class RegraIUpdate(UpdateView):
    model = RegraRateioItem
    form_class = FormRegraItem
    template_name = "regraI-add-alterar.html"
    success_url = reverse_lazy('regrarateio:regraList')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Obter empresa da sessão
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            from empresa.models import Empresa
            kwargs['empresa'] = Empresa.objects.get(id=empresa_id)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Editar Item de Rateio'
        context["titulo"] = 'Item de Rateio'
        context["acao"] = 'Atualizar'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Item de rateio atualizado com sucesso.")
        return super().form_valid(form)


class RegraIList(ListView):
    model = RegraRateioItem
    paginate_by = 10  # if pagination is desired
    template_name = "regraI-List.html"
    nomedaregra = "x"

    def get_queryset(self):
        empresa_id = self.request.session.get('empresa_id')
        nomeregra = get_object_or_404(RegraRateio, pk=self.kwargs['pk'], empresa_id=empresa_id)
        qs = super().get_queryset()
        qs = qs.order_by('-id').filter(regrarateio=nomeregra)
       
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa_id = self.request.session.get('empresa_id')
        nomeregra = get_object_or_404(RegraRateio, pk=self.kwargs['pk'], empresa_id=empresa_id)
        context['socios'] = Socio.objects.filter(empresa_id=empresa_id) if empresa_id else Socio.objects.none()
        
        context['regra'] = nomeregra
        if nomeregra.rateio == 'N':
            pass
        elif nomeregra.modo_alocacao == RegraRateio.MODO_PERCENTUAL:
            context['tot'] = RegraRateioItem.objects.filter(regrarateio=nomeregra).aggregate(
                Sum('percRateio')
            )

        context["descricao"] = f'Lista de Regra Rateio Item -  {nomeregra.nomedaregra}'
        context["table"] = "table table-light table-striped table-sm"
        
        return context

class RegraList(ListView):
    model = RegraRateio
    paginate_by = 10  # if pagination is desired
    template_name = "regra-List.html"

    def get_queryset(self):
        qs = super().get_queryset()
        eid = self.request.session.get('empresa_id')
        if eid:
            qs = qs.filter(empresa_id=eid)
        else:
            qs = qs.none()
        return qs.order_by('-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        eid = self.request.session.get('empresa_id')
        regraI = RegraRateioItem.objects.filter(regrarateio__empresa_id=eid) if eid else RegraRateioItem.objects.none()
        context['descricao'] = 'Lista de Regra Rateio'
        context['rgI'] = regraI
        context['table'] = 'table table-light table-striped table-sm'

        return context
    
                  


class RegraUpdate(UpdateView):
    model = RegraRateio
    form_class = FormRegraRateio
    template_name = 'regra-add-alterar.html'
    success_url = reverse_lazy('regrarateio:regraList')

    def get_queryset(self):
        qs = super().get_queryset()
        eid = self.request.session.get('empresa_id')
        if eid:
            return qs.filter(empresa_id=eid)
        return qs.none()

    def form_valid(self, form):
        messages.success(self.request, 'Regra de rateio atualizada com sucesso.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Alterar Regra de Rateio'
        context['titulo'] = 'Regra Rateio'
        context['acao'] = 'Atualizar'
        return context


def RegraDelete(request, pk):
    """View para excluir uma regra de rateio"""
    empresa_id = request.session.get('empresa_id')
    regra = get_object_or_404(RegraRateio, pk=pk, empresa_id=empresa_id)

    if request.method == 'POST':
        # Verificar se há itens de rateio associados
        itens_count = RegraRateioItem.objects.filter(regrarateio=regra).count()
        if itens_count > 0:
            messages.error(request, f'Não é possível excluir a regra "{regra.nomedaregra}" pois existem {itens_count} itens de rateio associados.')
            return redirect('regrarateio:regraList')

        lanc_count = LancamentoRateio.objects.filter(regra_rateio=regra).count()
        if lanc_count > 0:
            messages.error(
                request,
                f'Não é possível excluir a regra "{regra.nomedaregra}" pois existem {lanc_count} lançamentos de rateio gerados com ela.',
            )
            return redirect('regrarateio:regraList')

        regra.delete()
        messages.success(request, f'Regra de rateio "{regra.nomedaregra}" excluída com sucesso.')
        return redirect('regrarateio:regraList')

    context = {
        'regra': regra,
        'itens_count': RegraRateioItem.objects.filter(regrarateio=regra).count(),
        'titulo': f'Excluir Regra de Rateio',
        'descricao': f'Tem certeza que deseja excluir a regra "{regra.nomedaregra}"?'
    }

    return render(request, 'regra-delete.html', context)

def RegraIDelete(request, pk):
    """View para excluir um item de rateio"""
    empresa_id = request.session.get('empresa_id')
    item = get_object_or_404(
        RegraRateioItem.objects.select_related('regrarateio'),
        pk=pk,
        regrarateio__empresa_id=empresa_id,
    )

    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Item de rateio excluído com sucesso.')
        return redirect('regrarateio:regraList')

    context = {
        'item': item,
        'titulo': 'Excluir Item de Rateio',
        'descricao': f'Tem certeza que deseja excluir o item "{item.socios} - {item.percRateio}%"?'
    }

    return render(request, 'regraI-delete.html', context)


def _q_nao_dist_lucro_com_dtpg_especial():
    """Linhas que seguem filtro pela data do próprio lançamento (não dist. lucro com pgto no CAP)."""
    return (
        Q(conta_pagar__isnull=True)
        | ~Q(conta_pagar__categoria__tipo='L')
        | Q(conta_pagar__dtPag__isnull=True)
    )


def _q_dist_lucro_com_dtpg():
    """PGTO: categoria Distribuição de lucro e título com data de pagamento no CAP."""
    return Q(
        conta_pagar__categoria__tipo='L',
        conta_pagar__dtPag__isnull=False,
    )


_LANCAMENTO_RATEIO_FILTRO_CORE = ('data_inicio', 'data_fim', 'socio', 'tipo')

_LANCAMENTO_RATEIO_SORT_FIELDS = {
    'id': ['id'],
    'origem': ['origem'],
    'titulo': ['titulo_id_sort'],
    'modalidade': ['modalidade'],
    'cliente': ['conta_receber__cliente'],
    'viabilidade': ['viabilidade'],
    'obs_forma': ['obs_forma'],
    'valor_bruto': ['valor_bruto_sort'],
    'data': ['data_pagamento'],
    'tipo': ['tipo'],
    'descricao': ['descricao'],
    'regra': ['regra_rateio__codigo', 'regra_rateio__nomedaregra'],
    'socio': ['socio__socio', 'socio__lastname'],
    'obs_rateio': ['obs'],
    'valor': ['valor'],
}


def _sort_params_lancamento_rateio(request):
    sort = (request.GET.get('sort') or '').strip()
    dir_ = (request.GET.get('dir') or 'asc').strip().lower()
    if sort not in _LANCAMENTO_RATEIO_SORT_FIELDS:
        return '', 'asc'
    if dir_ not in ('asc', 'desc'):
        dir_ = 'asc'
    return sort, dir_


def _ordenar_queryset_lancamento_rateio(qs, request):
    sort, dir_ = _sort_params_lancamento_rateio(request)
    default = ('-data_pagamento', '-id')
    if not sort:
        return qs.order_by(*default)

    if sort in ('titulo', 'valor_bruto'):
        qs = qs.annotate(
            titulo_id_sort=Coalesce('conta_pagar_id', 'conta_receber_id'),
            valor_bruto_sort=Coalesce('conta_pagar__valorDoc', 'conta_receber__valor_a_receber'),
        )

    fields = list(_LANCAMENTO_RATEIO_SORT_FIELDS[sort])
    if dir_ == 'desc':
        order = ['-' + f for f in fields] + ['-id']
    else:
        order = fields + ['id']
    return qs.order_by(*order)


def _lancamento_rateio_list_query(request, extra=None, *, sort_override=None, dir_override=None):
    q = QueryDict(mutable=True)
    filtros = _filtros_efetivos_lancamento_rateio(request)
    for k, v in filtros.items():
        if v:
            q[k] = v
    for flag in ('abrir_convenio', 'abrir_obs_forma', 'abrir_cobranca'):
        v = (request.GET.get(flag) or '').strip()
        if v:
            q[flag] = v
    sort = sort_override if sort_override is not None else (request.GET.get('sort') or '').strip()
    dir_ = dir_override if dir_override is not None else (request.GET.get('dir') or 'asc').strip().lower()
    if sort and sort in _LANCAMENTO_RATEIO_SORT_FIELDS:
        q['sort'] = sort
        q['dir'] = dir_ if dir_ in ('asc', 'desc') else 'asc'
    if extra:
        for k, v in extra.items():
            if v is not None and str(v) != '':
                q[k] = str(v)
    return q.urlencode()


def _sort_url_lancamento_rateio(request, col):
    if col not in _LANCAMENTO_RATEIO_SORT_FIELDS:
        return '?' + _lancamento_rateio_list_query(request)
    cur_sort, cur_dir = _sort_params_lancamento_rateio(request)
    new_dir = 'desc' if cur_sort == col and cur_dir == 'asc' else 'asc'
    return '?' + _lancamento_rateio_list_query(request, sort_override=col, dir_override=new_dir)


def _session_key_lancamento_rateio_filtro(empresa_id):
    return f'lancamento_rateio_filtro_{empresa_id or 0}'


def _filtros_efetivos_lancamento_rateio(request):
    """Filtros da listagem: GET quando informado; senão última pesquisa na sessão."""
    empresa_id = request.session.get('empresa_id')
    sk = _session_key_lancamento_rateio_filtro(empresa_id)

    if any((request.GET.get(k) or '').strip() for k in _LANCAMENTO_RATEIO_FILTRO_CORE):
        data = {k: (request.GET.get(k) or '').strip() for k in _LANCAMENTO_RATEIO_FILTRO_CORE}
        ad = (request.GET.get('ad_irpj_periodo') or '').strip()
        if ad:
            data['ad_irpj_periodo'] = ad
        request.session[sk] = data
        request.session.modified = True
        return data

    saved = dict(request.session.get(sk) or {})
    ad_get = (request.GET.get('ad_irpj_periodo') or '').strip()
    if ad_get:
        saved['ad_irpj_periodo'] = ad_get
    return saved


def _url_lancamento_rateio_list_com_filtro(request, extra=None):
    qs = _lancamento_rateio_list_query(request, extra=extra)
    if qs:
        return reverse('regrarateio:lancamentoRateioList') + '?' + qs
    return reverse('regrarateio:lancamentoRateioList')


def redirect_lancamento_rateio_list(request, extra=None):
    return redirect(_url_lancamento_rateio_list_com_filtro(request, extra=extra))


def _filtra_queryset_lancamento_rateio_por_periodo(qs, di, df):
    """
    Aplica filtro de data ao queryset de LancamentoRateio.

    Regra: na maioria dos casos usa ``data_pagamento`` do lançamento.
    Para contas a pagar com categoria «Distribuição de lucro» (L) e ``dtPag``
    preenchida no título, o período é pela **data de emissão** do CAP; se não
    houver emissão, usa ``data_pagamento`` do lançamento.
    """
    if not di and not df:
        return qs
    q_pad = _q_nao_dist_lucro_com_dtpg_especial()
    q_dist = _q_dist_lucro_com_dtpg()
    if di and df:
        if di > df:
            di, df = df, di
        return qs.filter(
            (q_pad & Q(data_pagamento__gte=di, data_pagamento__lte=df))
            | (
                q_dist
                & (
                    Q(
                        conta_pagar__dtEmissao__gte=di,
                        conta_pagar__dtEmissao__lte=df,
                        conta_pagar__dtEmissao__isnull=False,
                    )
                    | Q(
                        conta_pagar__dtEmissao__isnull=True,
                        data_pagamento__gte=di,
                        data_pagamento__lte=df,
                    )
                )
            )
        )
    if di:
        return qs.filter(
            (q_pad & Q(data_pagamento__gte=di))
            | (
                q_dist
                & (
                    Q(conta_pagar__dtEmissao__gte=di, conta_pagar__dtEmissao__isnull=False)
                    | Q(conta_pagar__dtEmissao__isnull=True, data_pagamento__gte=di)
                )
            )
        )
    # só df
    return qs.filter(
        (q_pad & Q(data_pagamento__lte=df))
        | (
            q_dist
            & (
                Q(conta_pagar__dtEmissao__lte=df, conta_pagar__dtEmissao__isnull=False)
                | Q(conta_pagar__dtEmissao__isnull=True, data_pagamento__lte=df)
            )
        )
    )


class LancamentoRateioList(ListView):
    model = LancamentoRateio
    paginate_by = 30
    template_name = 'lancamento-rateio-list.html'

    def get(self, request, *args, **kwargs):
        if request.GET.get('limpar'):
            empresa_id = request.session.get('empresa_id')
            sk = _session_key_lancamento_rateio_filtro(empresa_id)
            if sk in request.session:
                del request.session[sk]
                request.session.modified = True
            return redirect_lancamento_rateio_list(request)

        has_core = any(
            (request.GET.get(k) or '').strip() for k in _LANCAMENTO_RATEIO_FILTRO_CORE
        )
        if not has_core:
            empresa_id = request.session.get('empresa_id')
            saved = request.session.get(_session_key_lancamento_rateio_filtro(empresa_id)) or {}
            if any(saved.get(k) for k in _LANCAMENTO_RATEIO_FILTRO_CORE):
                q = QueryDict(mutable=True)
                for k in _LANCAMENTO_RATEIO_FILTRO_CORE:
                    if saved.get(k):
                        q[k] = saved[k]
                ad = (request.GET.get('ad_irpj_periodo') or saved.get('ad_irpj_periodo') or '').strip()
                if ad:
                    q['ad_irpj_periodo'] = ad
                for flag in ('abrir_convenio', 'abrir_obs_forma', 'abrir_cobranca', 'page', 'sort', 'dir'):
                    v = (request.GET.get(flag) or '').strip()
                    if v:
                        q[flag] = v
                return redirect(reverse('regrarateio:lancamentoRateioList') + '?' + q.urlencode())

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        from contasareceber.models import BaixaContaAReceber
        from django.db.models import Prefetch

        baixas_qs = BaixaContaAReceber.objects.select_related(
            'conta_banco',
            'conta_banco__banco',
        ).order_by('-data_recebimento', '-id')

        qs = LancamentoRateio.objects.select_related(
            'regra_rateio',
            'socio',
            'conta_pagar',
            'conta_pagar__categoria',
            'conta_pagar__cobranca',
            'conta_pagar__conta_banco',
            'conta_pagar__conta_banco__banco',
            'conta_receber',
            'conta_receber__nota',
            'conta_receber__forma_pagamento',
            'conta_receber__conta_banco',
            'conta_receber__conta_banco__banco',
        ).prefetch_related(
            Prefetch(
                'conta_receber__baixas',
                queryset=baixas_qs,
                to_attr='baixas_ordenadas',
            ),
        )
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        filtros = _filtros_efetivos_lancamento_rateio(self.request)
        di = parse_date((filtros.get('data_inicio') or '').strip() or '')
        df = parse_date((filtros.get('data_fim') or '').strip() or '')
        qs = _filtra_queryset_lancamento_rateio_por_periodo(qs, di, df)

        socio_raw = (filtros.get('socio') or '').strip()
        if socio_raw.isdigit():
            qs = qs.filter(socio_id=int(socio_raw))

        tipo = (filtros.get('tipo') or '').strip()
        if tipo in (
            LancamentoRateio.TIPO_PGTO,
            LancamentoRateio.TIPO_RECEBIMENTO,
            LancamentoRateio.TIPO_DEDUCAO_RECEITA,
        ):
            qs = qs.filter(tipo=tipo)

        return _ordenar_queryset_lancamento_rateio(qs, self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa_id = self.request.session.get('empresa_id')
        from socio.models import Socio

        context['socios'] = (
            Socio.objects.filter(empresa_id=empresa_id).order_by('socio', 'lastname')
            if empresa_id
            else Socio.objects.none()
        )
        filtros = _filtros_efetivos_lancamento_rateio(self.request)
        context['filtro_data_inicio'] = filtros.get('data_inicio', '')
        context['filtro_data_fim'] = filtros.get('data_fim', '')
        socio_get = (filtros.get('socio') or '').strip()
        context['filtro_socio'] = socio_get
        context['filtro_socio_id'] = int(socio_get) if socio_get.isdigit() else None
        context['filtro_tipo'] = (filtros.get('tipo') or '').strip()
        context['tipo_choices'] = LancamentoRateio.TIPO_CHOICES
        sort_col, sort_dir = _sort_params_lancamento_rateio(self.request)
        context['sort_col'] = sort_col
        context['sort_dir'] = sort_dir
        context['sort_urls'] = {
            col: _sort_url_lancamento_rateio(self.request, col)
            for col in _LANCAMENTO_RATEIO_SORT_FIELDS
        }
        context['filter_query'] = _lancamento_rateio_list_query(self.request)
        context['voltar_list_url'] = _url_lancamento_rateio_list_com_filtro(self.request)
        context['regras_rateio_modal'] = (
            RegraRateio.objects.filter(empresa_id=empresa_id)
            .annotate(n_itens=Count('regrarateioitem'))
            .order_by('codigo', 'nomedaregra')
            if empresa_id
            else RegraRateio.objects.none()
        )
        context['regras_rateio_meta_json'] = _regras_itens_json_por_empresa(empresa_id)

        # Totais do conjunto filtrado (todas as páginas), não só da página atual
        qs_filtro = self.get_queryset()
        agg = qs_filtro.aggregate(
            total_qtd=Count('id'),
            total_valor=Sum('valor'),
        )
        tot_pg = qs_filtro.filter(
            tipo__in=(LancamentoRateio.TIPO_PGTO, LancamentoRateio.TIPO_DEDUCAO_RECEITA)
        ).aggregate(s=Sum('valor'))
        tot_rec = qs_filtro.filter(tipo=LancamentoRateio.TIPO_RECEBIMENTO).aggregate(s=Sum('valor'))

        def _to_dec(x):
            if x is None:
                return Decimal('0')
            return x if isinstance(x, Decimal) else Decimal(str(x))

        v_total = _to_dec(agg['total_valor'])
        v_pg = _to_dec(tot_pg.get('s'))
        v_rec = _to_dec(tot_rec.get('s'))

        context['total_qtd'] = int(agg['total_qtd'] or 0)
        context['total_valor'] = v_total
        context['total_pgto'] = v_pg
        context['total_recebimento'] = v_rec
        # Texto já formatado (evita branco no template com Decimal/floatformat em alguns ambientes)
        context['total_valor_txt'] = f'{v_total:.2f}'.replace('.', ',')
        context['total_pgto_txt'] = f'{v_pg:.2f}'.replace('.', ',')
        context['total_recebimento_txt'] = f'{v_rec:.2f}'.replace('.', ',')

        # Cards por sócio: totais de recebimento (receita) e pagamento (despesa) no filtro.
        raw_pg = {}
        raw_rec = {}
        for sid, tipo, valor in qs_filtro.values_list('socio_id', 'tipo', 'valor'):
            if sid is None:
                continue
            v = _to_dec(valor)
            if tipo in (LancamentoRateio.TIPO_PGTO, LancamentoRateio.TIPO_DEDUCAO_RECEITA):
                raw_pg[sid] = raw_pg.get(sid, Decimal('0')) + v
            elif tipo == LancamentoRateio.TIPO_RECEBIMENTO:
                raw_rec[sid] = raw_rec.get(sid, Decimal('0')) + v

        def _card_socio_dict(nome, extra, pg, rec):
            pg_abs = abs(pg)
            saldo = rec + pg
            return {
                'nome': nome,
                'extra': extra,
                'pgto_abs_txt': _fmt_br_moeda(pg_abs),
                'recebimento_txt': _fmt_br_moeda(rec),
                'saldo_txt': _fmt_br_moeda(saldo),
                'tem_pgto': pg_abs > 0,
                'tem_recebimento': rec > 0,
                '_sort_rec': rec,
                '_sort_pg': pg_abs,
            }

        ids_empresa = {s.id for s in context['socios']}
        sids_com_movimento = set(raw_pg) | set(raw_rec)
        cards_socios = []
        for s in context['socios']:
            pg = raw_pg.get(s.id, Decimal('0'))
            rec = raw_rec.get(s.id, Decimal('0'))
            if pg == 0 and rec == 0:
                continue
            cards_socios.append(_card_socio_dict(str(s), False, pg, rec))
        extras_ids = sorted(sids_com_movimento - ids_empresa)
        for sid in extras_ids:
            pg = raw_pg.get(sid, Decimal('0'))
            rec = raw_rec.get(sid, Decimal('0'))
            if pg == 0 and rec == 0:
                continue
            try:
                s_obj = Socio.objects.get(pk=sid)
                nome = str(s_obj)
            except Socio.DoesNotExist:
                nome = f'Sócio #{sid} (cadastro não encontrado)'
            cards_socios.append(_card_socio_dict(nome, True, pg, rec))
        cards_socios.sort(key=lambda c: (c['_sort_rec'], c['_sort_pg']), reverse=True)
        for c in cards_socios:
            c.pop('_sort_rec', None)
            c.pop('_sort_pg', None)
        context['cards_socios'] = cards_socios

        from regrarateio.convenio_viabilidade import coletar_totais_por_viabilidade_convenio

        periodo_ad = (filtros.get('ad_irpj_periodo') or 'mensal').strip().lower()
        if periodo_ad not in ('mensal', 'trimestral'):
            periodo_ad = 'mensal'
        tot_conv = coletar_totais_por_viabilidade_convenio(
            empresa_id, qs_filtro, periodo_ad_irpj=periodo_ad
        )
        for linha in tot_conv['linhas']:
            linha['total_txt'] = _fmt_br_moeda(linha['total'])
            linha['iss_ap_txt'] = _fmt_br_moeda(linha['iss_ap'])
            linha['pis_ap_txt'] = _fmt_br_moeda(linha['pis_ap'])
            linha['cofins_ap_txt'] = _fmt_br_moeda(linha['cofins_ap'])
            linha['csll_ap_txt'] = _fmt_br_moeda(linha['csll_ap'])
            linha['irpj_ap_txt'] = _fmt_br_moeda(linha['irpj_ap'])
            linha['impostos_ap_txt'] = _fmt_br_moeda(linha['impostos_ap'])
            linha['ad_irpj_txt'] = _fmt_br_moeda(linha['ad_irpj'])
            linha['total_imposto_txt'] = _fmt_br_moeda(linha.get('total_imposto'))
            linha['liquido_ap_txt'] = _fmt_br_moeda(linha['liquido_ap'])
        for out in tot_conv['outros']:
            out['total_txt'] = _fmt_br_moeda(out['total'])
        ad = tot_conv.get('ad_irpj') or {}
        context['filtro_ad_irpj_periodo'] = periodo_ad
        context['totais_convenio_viabilidade'] = tot_conv
        context['totais_convenio_total_txt'] = _fmt_br_moeda(tot_conv['total_geral'])
        context['totais_convenio_impostos_txt'] = _fmt_br_moeda(tot_conv['total_impostos_ap'])
        context['totais_convenio_ad_irpj_txt'] = _fmt_br_moeda(tot_conv['total_ad_irpj'])
        context['totais_convenio_total_imposto_txt'] = _fmt_br_moeda(tot_conv['total_imposto'])
        context['totais_convenio_liquido_txt'] = _fmt_br_moeda(tot_conv['total_liquido_ap'])
        context['totais_convenio_irpj_txt'] = _fmt_br_moeda(tot_conv['total_irpj_ap'])
        context['totais_convenio_irpj_mais_ad_txt'] = _fmt_br_moeda(tot_conv['total_irpj_mais_ad'])
        cols = tot_conv.get('totais_colunas') or {}
        context['totais_convenio_qtd'] = cols.get('qtd', 0)
        context['totais_convenio_iss_txt'] = _fmt_br_moeda(cols.get('iss_ap'))
        context['totais_convenio_pis_txt'] = _fmt_br_moeda(cols.get('pis_ap'))
        context['totais_convenio_cofins_txt'] = _fmt_br_moeda(cols.get('cofins_ap'))
        context['totais_convenio_csll_txt'] = _fmt_br_moeda(cols.get('csll_ap'))
        di_conv = parse_date((filtros.get('data_inicio') or '').strip() or '')
        df_conv = parse_date((filtros.get('data_fim') or '').strip() or '')
        meses_pt = [
            '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
        ]
        if di_conv and df_conv and di_conv.year == df_conv.year and di_conv.month == df_conv.month:
            context['convenio_periodo_label'] = f'{meses_pt[di_conv.month]}/{di_conv.year}'
        elif di_conv and df_conv:
            context['convenio_periodo_label'] = (
                f'{di_conv.strftime("%d/%m/%Y")} a {df_conv.strftime("%d/%m/%Y")}'
            )
        elif di_conv:
            context['convenio_periodo_label'] = f'A partir de {di_conv.strftime("%d/%m/%Y")}'
        elif df_conv:
            context['convenio_periodo_label'] = f'Até {df_conv.strftime("%d/%m/%Y")}'
        else:
            context['convenio_periodo_label'] = 'Período do filtro'
        context['ad_irpj_base_lucro_txt'] = _fmt_br_moeda(ad.get('base_lucro'))
        context['ad_irpj_excedente_txt'] = _fmt_br_moeda(ad.get('excedente'))
        context['ad_irpj_total_txt'] = _fmt_br_moeda(ad.get('ad_irpj_total'))
        context['ad_irpj_limite_txt'] = _fmt_br_moeda(ad.get('limite'))
        indice = ad.get('indice') or Decimal('0')
        context['ad_irpj_indice_txt'] = f'{indice:.10f}'.replace('.', ',')

        from regrarateio.convenio_imposto_rateio import (
            IMPOSTO_DIA_PAGAMENTO,
            _chave_periodo,
            impostos_convenio_ja_lancados,
            impostos_pendentes_lancamento,
            mes_referencia_unico,
        )

        chave_conv = _chave_periodo(di_conv, df_conv)
        ja_imp = (
            impostos_convenio_ja_lancados(empresa_id, chave_conv)
            if empresa_id and tot_conv.get('linhas')
            else []
        )
        mes_unico = mes_referencia_unico(di_conv, df_conv) is not None
        pendentes = (
            impostos_pendentes_lancamento(tot_conv, ja_imp)
            if tot_conv.get('linhas')
            else []
        )
        context['convenio_mes_unico'] = mes_unico
        context['convenio_impostos_ja_lancados'] = ja_imp
        context['convenio_impostos_pendentes'] = pendentes
        context['convenio_impostos_todos_lancados'] = mes_unico and bool(ja_imp) and not pendentes
        context['convenio_imposto_dias_pagamento'] = IMPOSTO_DIA_PAGAMENTO

        from regrarateio.obs_forma_totalizadores import coletar_totais_obs_forma

        obs_forma_data = coletar_totais_obs_forma(qs_filtro)
        context['empresa_id'] = empresa_id
        obs_forma_linhas = []
        for row in obs_forma_data['por_obs_forma']:
            obs_forma_linhas.append({
                'obs_forma': row['obs_forma'],
                'valor': row['valor'],
                'qtd': row['qtd'],
                'valor_txt': _fmt_br_moeda(row['valor']),
            })
        context['obs_forma_linhas'] = obs_forma_linhas
        context['obs_forma_totalizadores_json'] = json.dumps(
            {
                'por_obs_forma': [
                    {
                        'obs_forma': row['obs_forma'],
                        'valor': str(row['valor'].quantize(Decimal('0.01'))),
                        'qtd': row['qtd'],
                    }
                    for row in obs_forma_data['por_obs_forma']
                ],
                'celulas': obs_forma_data['celulas'],
            },
            ensure_ascii=False,
        )
        context['convenio_periodo_label_obs'] = context.get('convenio_periodo_label', 'Período do filtro')

        from regrarateio.cobranca_totalizadores import coletar_totais_cobranca

        cobranca_data = coletar_totais_cobranca(qs_filtro)
        cobranca_linhas = []
        for row in cobranca_data['por_cobranca']:
            cobranca_linhas.append({
                'cobranca': row['cobranca'],
                'valor': row['valor'],
                'qtd': row['qtd'],
                'valor_txt': _fmt_br_moeda(row['valor']),
            })
        context['cobranca_linhas'] = cobranca_linhas
        context['cobranca_totalizadores_json'] = json.dumps(
            {
                'por_cobranca': [
                    {
                        'cobranca': row['cobranca'],
                        'valor': str(row['valor'].quantize(Decimal('0.01'))),
                        'qtd': row['qtd'],
                    }
                    for row in cobranca_data['por_cobranca']
                ],
                'celulas': cobranca_data['celulas'],
            },
            ensure_ascii=False,
        )
        context['convenio_periodo_label_cobranca'] = context.get('convenio_periodo_label', 'Período do filtro')

        return context


def _fmt_br_moeda(d):
    """Decimal ou número → texto brasileiro com milhares (ex.: 46024,75 → '46.024,75')."""
    if d is None:
        return '0,00'
    x = d if isinstance(d, Decimal) else Decimal(str(d))
    neg = x < 0
    a = abs(x).quantize(Decimal('0.01'))
    s = f'{a:.2f}'
    int_part, frac = s.split('.')
    n = len(int_part)
    chunks = []
    i = n
    while i > 0:
        chunks.insert(0, int_part[max(0, i - 3) : i])
        i -= 3
    int_grp = '.'.join(chunks)
    out = f'{int_grp},{frac}'
    return ('-' if neg else '') + out


def _fmt_br_decimal(d):
    if d is None:
        return '0,00'
    return f'{d:.2f}'.replace('.', ',')


def _regras_itens_json_por_empresa(empresa_id):
    if not empresa_id:
        return '{}'
    regras = RegraRateio.objects.filter(empresa_id=empresa_id).order_by('nomedaregra')
    out = {}
    for r in regras:
        itens = (
            RegraRateioItem.objects.filter(regrarateio=r)
            .select_related('socios')
            .order_by('socios_id')
        )
        manual = None
        item_rows = []
        for i in itens:
            if i.tipo_participacao == RegraRateioItem.TIPO_MANUAL:
                manual = {'socio_id': i.socios_id, 'nome': str(i.socios)}
            item_rows.append(
                {
                    'socio_id': i.socios_id,
                    'nome': str(i.socios),
                    'perc': str(i.percRateio or 0),
                    'tipo': i.tipo_participacao,
                }
            )
        out[str(r.pk)] = {
            'modo': r.modo_alocacao,
            'manual': manual,
            'itens': item_rows,
        }
    return json.dumps(out, ensure_ascii=False)


def _parse_valores_rateio_post(request, titulo_ids):
    """Lê campos ``valor_rateio_{titulo_id}_{socio_id}`` do POST."""
    out = {}
    titulo_set = set(int(x) for x in titulo_ids)
    prefix = 'valor_rateio_'
    for key in request.POST:
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        parts = rest.split('_', 1)
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        tid, sid = int(parts[0]), int(parts[1])
        if tid not in titulo_set:
            continue
        raw = (request.POST.get(key) or '').strip().replace(',', '.')
        if not raw:
            continue
        try:
            val = Decimal(raw)
        except Exception:
            continue
        out.setdefault(tid, {})[sid] = val
    return out


def _resumo_titulo_principal(lanc):
    base = valor_base_titulo_de_lancamento(lanc)
    if lanc.conta_pagar_id:
        cap = lanc.conta_pagar
        return {
            'tipo_origem': 'pagar',
            'titulo_id': cap.id,
            'descricao': cap.descricao or '',
            'parceiro': str(cap.fornecedor) if cap.fornecedor_id else '',
            'valor_base': base,
            'valor_base_txt': _fmt_br_decimal(base),
            'data_ref': cap.dtPag or cap.dtvenc,
            'status': cap.get_status_display(),
            'numdoc': cap.numdoc or '',
        }
    car = lanc.conta_receber
    return {
        'tipo_origem': 'receber',
        'titulo_id': car.id,
        'descricao': (car.observacao or car.doc or '')[:255] or car.cliente or '',
        'parceiro': car.cliente or '',
        'valor_base': base,
        'valor_base_txt': _fmt_br_decimal(base),
        'data_ref': car.data_recebimento or car.data_vencimento,
        'status': car.get_status_display(),
        'numdoc': car.doc or '',
    }


def _obs_inicial_grupo_rateio(linhas_qs):
    linhas = list(linhas_qs)
    if not linhas:
        return ''
    return linhas[0].obs_rateio_exibicao()[:255]


def _linhas_atuais_com_perc(linhas_qs, valor_base, regra):
    item_map = {}
    if regra_id := (regra.pk if regra else None):
        item_map = {
            i.socios_id: i.percRateio
            for i in RegraRateioItem.objects.filter(regrarateio_id=regra_id)
        }
    rows = []
    vb = valor_base if valor_base and valor_base != 0 else Decimal('1')
    for row in linhas_qs:
        perc = item_map.get(row.socio_id)
        if perc is None:
            perc = (abs(row.valor) * Decimal('100')) / vb
            perc = perc.quantize(Decimal('0.01'))
        rows.append(
            {
                'id': row.id,
                'socio': str(row.socio),
                'valor': row.valor,
                'valor_txt': _fmt_br_decimal(row.valor),
                'perc': perc,
                'obs': row.obs_rateio_exibicao(),
            }
        )
    return rows


class LancamentoRateioGrupoEdit(View):
    """Edita o rateio do título inteiro: mostra o lançamento principal e todas as linhas; troca de regra recalcula todos."""

    template_name = 'lancamento-rateio-editar.html'

    def get_lancamento_por_titulo(self, origem, titulo_id):
        """
        origem: 'cap' (conta a pagar) ou 'car' (conta a receber).
        titulo_id: ID do título (ContasaPagar ou ContaAReceber), não do lançamento de rateio.
        """
        origem = (origem or '').lower()
        if origem not in ('cap', 'car'):
            raise Http404

        qs = (
            LancamentoRateio.objects.select_related(
                'regra_rateio',
                'socio',
                'conta_pagar',
                'conta_pagar__fornecedor',
                'conta_receber',
                'empresa',
            )
            .order_by('id')
        )
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        if origem == 'cap':
            qs = qs.filter(conta_pagar_id=titulo_id)
        else:
            qs = qs.filter(conta_receber_id=titulo_id)

        lanc = qs.first()
        if not lanc:
            raise Http404('Não há lançamentos de rateio para este título ou o título não pertence à empresa.')
        return lanc

    def get_grupo_queryset(self, lanc):
        if lanc.conta_pagar_id:
            return LancamentoRateio.objects.filter(conta_pagar_id=lanc.conta_pagar_id).select_related(
                'socio', 'regra_rateio'
            )
        return LancamentoRateio.objects.filter(conta_receber_id=lanc.conta_receber_id).select_related(
            'socio', 'regra_rateio'
        )

    def get(self, request, origem, titulo_id):
        lanc = self.get_lancamento_por_titulo(origem, titulo_id)
        linhas = self.get_grupo_queryset(lanc).order_by('socio_id')
        empresa_id = request.session.get('empresa_id')
        valor_base = valor_base_titulo_de_lancamento(lanc)
        regra_atual = lanc.regra_rateio
        principal = _resumo_titulo_principal(lanc)
        linhas_det = _linhas_atuais_com_perc(linhas, valor_base, regra_atual)

        form = FormRecalcularRateioGrupo(
            initial={
                'regra_rateio': regra_atual.pk if regra_atual else None,
                'obs_rateio': _obs_inicial_grupo_rateio(linhas),
            },
            empresa_id=empresa_id,
        )

        preview_inicial = []
        if regra_atual and valor_base:
            preview_inicial = preview_linhas_rateio_por_regra(
                regra_atual.pk, valor_base, lanc.tipo, empresa_id=lanc.empresa_id
            )

        ctx = {
            'titulo': 'Editar rateio do título',
            'lancamento_ref': lanc,
            'principal': principal,
            'linhas_det': linhas_det,
            'linhas_count': linhas.count(),
            'valor_base': valor_base,
            'valor_base_str': str(valor_base),
            'tipo_lanc': lanc.tipo,
            'form': form,
            'regras_itens_json': _regras_itens_json_por_empresa(empresa_id),
            'preview_inicial_json': json.dumps(preview_inicial, ensure_ascii=False),
            'voltar_list_url': _url_lancamento_rateio_list_com_filtro(request),
        }
        return render(request, self.template_name, ctx)

    def post(self, request, origem, titulo_id):
        lanc = self.get_lancamento_por_titulo(origem, titulo_id)
        empresa_id = request.session.get('empresa_id')
        form = FormRecalcularRateioGrupo(request.POST, empresa_id=empresa_id)

        linhas = self.get_grupo_queryset(lanc).order_by('socio_id')
        valor_base = valor_base_titulo_de_lancamento(lanc)
        regra_atual = lanc.regra_rateio
        principal = _resumo_titulo_principal(lanc)
        linhas_det = _linhas_atuais_com_perc(linhas, valor_base, regra_atual)

        if form.is_valid():
            nova = form.cleaned_data['regra_rateio']
            try:
                if nova is None:
                    n, = remover_rateio_do_titulo(lanc.pk)
                    messages.success(
                        request,
                        f'Rateio removido: {n} lançamento(s) excluído(s) e regra limpa no título.',
                    )
                else:
                    valores_manuais = None
                    itens_nova = list(RegraRateioItem.objects.filter(regrarateio=nova))
                    if _regra_usa_valor_manual(nova, itens_nova):
                        manual_item = next(
                            (i for i in itens_nova if i.tipo_participacao == RegraRateioItem.TIPO_MANUAL),
                            None,
                        )
                        if manual_item:
                            valores_manuais = {
                                manual_item.socios_id: form.cleaned_data['valor_manual'],
                            }
                    obs_rateio = (form.cleaned_data.get('obs_rateio') or '').strip()[:255]
                    n, = reaplicar_regra_no_titulo(
                        lanc.pk, nova.pk, valores_manuais=valores_manuais, obs_rateio=obs_rateio
                    )
                    messages.success(
                        request,
                        f'Rateio atualizado: {n} linha(s) gravada(s) conforme a regra «{nova}».',
                    )
                return redirect_lancamento_rateio_list(request)
            except ValueError as exc:
                messages.error(request, str(exc))

        preview_inicial = []
        sel = form.data.get('regra_rateio')
        if sel and str(sel).isdigit():
            preview_inicial = preview_linhas_rateio_por_regra(
                int(sel), valor_base, lanc.tipo, empresa_id=lanc.empresa_id
            )

        ctx = {
            'titulo': 'Editar rateio do título',
            'lancamento_ref': lanc,
            'principal': principal,
            'linhas_det': linhas_det,
            'linhas_count': linhas.count(),
            'valor_base': valor_base,
            'valor_base_str': str(valor_base),
            'tipo_lanc': lanc.tipo,
            'form': form,
            'regras_itens_json': _regras_itens_json_por_empresa(empresa_id),
            'preview_inicial_json': json.dumps(preview_inicial, ensure_ascii=False),
            'voltar_list_url': _url_lancamento_rateio_list_com_filtro(request),
        }
        return render(request, self.template_name, ctx)


def lancamento_rateio_delete(request, pk):
    empresa_id = request.session.get('empresa_id')
    qs = LancamentoRateio.objects.all()
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    lancamento = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        lancamento.delete()
        messages.success(request, 'Lançamento de rateio excluído com sucesso.')
        return redirect_lancamento_rateio_list(request)

    context = {
        'lancamento': lancamento,
        'titulo': 'Excluir lançamento de rateio',
        'descricao': (
            f'Confirma a exclusão deste lançamento? '
            f'{lancamento.get_tipo_display()} — {lancamento.socio} — valor {lancamento.valor}'
        ),
        'voltar_list_url': _url_lancamento_rateio_list_com_filtro(request),
    }
    return render(request, 'lancamento-rateio-delete.html', context)


def contas_pagar_rateio_candidatas(request):
    """GET JSON: lista contas a pagar elegíveis no período (para o modal de rateio)."""
    if request.method != 'GET':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'erro': 'Selecione uma empresa no menu.'}, status=400)

    di = parse_date(request.GET.get('data_inicio', '') or '')
    df = parse_date(request.GET.get('data_fim', '') or '')
    if not di or not df:
        return JsonResponse({'erro': 'Informe data inicial e data final.'}, status=400)
    if di > df:
        return JsonResponse({'erro': 'A data inicial não pode ser maior que a final.'}, status=400)

    somente_pagos = (request.GET.get('somente_pagos') or '').strip() == '1'
    filtro_descricao = (request.GET.get('descricao') or '').strip()
    filtro_fornecedor = (request.GET.get('fornecedor') or '').strip()
    filtro_centro_custo = (request.GET.get('centro_custo') or '').strip()

    try:
        contas = query_contas_pagar_rateio_candidatas(
            empresa_id,
            di,
            df,
            alinhado_grade_resumo=somente_pagos,
            filtro_descricao=filtro_descricao,
            filtro_fornecedor=filtro_fornecedor,
            filtro_centro_custo=filtro_centro_custo,
        )
    except Exception as exc:
        return JsonResponse({'erro': str(exc)}, status=500)

    return JsonResponse({'contas': contas})


def contas_receber_rateio_candidatas(request):
    """GET JSON: lista contas a receber pagas no período (modal de rateio)."""
    if request.method != 'GET':
        return JsonResponse({'erro': 'Método não permitido.'}, status=405)

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'erro': 'Selecione uma empresa no menu.'}, status=400)

    di = parse_date(request.GET.get('data_inicio', '') or '')
    df = parse_date(request.GET.get('data_fim', '') or '')
    if not di or not df:
        return JsonResponse({'erro': 'Informe data inicial e data final.'}, status=400)
    if di > df:
        return JsonResponse({'erro': 'A data inicial não pode ser maior que a final.'}, status=400)

    try:
        contas = query_contas_receber_rateio_candidatas(empresa_id, di, df)
    except Exception as exc:
        return JsonResponse({'erro': str(exc)}, status=500)

    return JsonResponse({'contas': contas})


def gerar_rateio_contas_pagar_aplicar(request):
    """POST: aplica regra de rateio nas contas a pagar selecionadas e grava lançamentos."""
    if request.method != 'POST':
        return redirect_lancamento_rateio_list(request)

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect_lancamento_rateio_list(request)

    raw_ids = request.POST.getlist('conta_pagar_id')
    ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]

    if not ids:
        messages.error(request, 'Selecione ao menos uma conta a pagar.')
        return redirect_lancamento_rateio_list(request)

    rid = (request.POST.get('regra_rateio') or '').strip()
    regra_id_forcar = int(rid) if rid.isdigit() else None
    origem_pagos = (request.POST.get('origem_pagos') or '').strip() == '1'

    valores_por_titulo = _parse_valores_rateio_post(request, ids)

    try:
        criados, ignorados = gerar_rateio_contas_pagar(
            empresa_id=empresa_id,
            conta_pagar_ids=ids,
            regra_id_forcar=regra_id_forcar,
            origem_pagos=origem_pagos,
            valores_por_titulo=valores_por_titulo or None,
        )
        if criados > 0:
            messages.success(
                request,
                f'Rateio aplicado: {criados} lançamento(s) gravado(s). '
                f'Ignorados (já gerados ou sem regra/itens na regra): {ignorados}.',
            )
        else:
            messages.warning(
                request,
                'Nenhum lançamento foi gerado. Escolha uma regra no modal (lista "Regra de rateio a aplicar") '
                'ou cadastre a regra no título em Contas a pagar; a regra precisa ter sócios e percentuais. '
                f'Títulos não processados nesta execução: {ignorados}.',
            )
    except Exception as exc:
        messages.error(request, f'Erro ao gerar rateio: {exc}')

    return redirect_lancamento_rateio_list(request)


def gerar_rateio_contas_receber_aplicar(request):
    """POST: aplica regra nas contas a receber selecionadas no modal (valores positivos no rateio)."""
    if request.method != 'POST':
        return redirect_lancamento_rateio_list(request)

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect_lancamento_rateio_list(request)

    raw_ids = request.POST.getlist('conta_receber_id')
    ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]

    if not ids:
        messages.error(request, 'Selecione ao menos uma conta a receber.')
        return redirect_lancamento_rateio_list(request)

    rid = (request.POST.get('regra_rateio') or '').strip()
    regra_id_forcar = int(rid) if rid.isdigit() else None

    valores_por_titulo = _parse_valores_rateio_post(request, ids)

    try:
        criados, ignorados = gerar_rateio_contas_receber(
            empresa_id=empresa_id,
            conta_receber_ids=ids,
            regra_id_forcar=regra_id_forcar,
            valores_por_titulo=valores_por_titulo or None,
        )
        if criados > 0:
            messages.success(
                request,
                f'Rateio (contas a receber): {criados} lançamento(s) gravado(s) com valores positivos. '
                f'Ignorados (já gerados ou sem regra/itens): {ignorados}.',
            )
        else:
            messages.warning(
                request,
                'Nenhum lançamento foi gerado. Escolha uma regra no modal ou cadastre a regra no título; '
                'a regra precisa ter sócios e percentuais. '
                f'Títulos não processados: {ignorados}.',
            )
    except Exception as exc:
        messages.error(request, f'Erro ao gerar rateio: {exc}')

    return redirect_lancamento_rateio_list(request)


def gerar_rateio_impostos_convenio_aplicar(request):
    """POST: lança ISS, PIS, COFINS, CSLL e IRPJ (ap.+ Ad.) como PGTO origem TOTAL CONVENIO."""
    if request.method != 'POST':
        return redirect_lancamento_rateio_list(request)

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect_lancamento_rateio_list(request)

    rid = (request.POST.get('regra_rateio') or '').strip()
    regra_id = int(rid) if rid.isdigit() else None
    if not regra_id:
        messages.error(request, 'Selecione a regra de rateio para os impostos.')
        return redirect_lancamento_rateio_list(request, extra={'abrir_convenio': '1'})

    di = parse_date((request.POST.get('data_inicio') or '').strip() or '')
    df = parse_date((request.POST.get('data_fim') or '').strip() or '')
    periodo_ad = (request.POST.get('ad_irpj_periodo') or 'mensal').strip().lower()
    if periodo_ad not in ('mensal', 'trimestral'):
        periodo_ad = 'mensal'
    qs = LancamentoRateio.objects.filter(empresa_id=empresa_id)
    qs = _filtra_queryset_lancamento_rateio_por_periodo(qs, di, df)
    socio_raw = (request.POST.get('socio') or '').strip()
    if socio_raw.isdigit():
        qs = qs.filter(socio_id=int(socio_raw))
    tipo = (request.POST.get('tipo') or '').strip()
    if tipo in (
        LancamentoRateio.TIPO_PGTO,
        LancamentoRateio.TIPO_RECEBIMENTO,
        LancamentoRateio.TIPO_DEDUCAO_RECEITA,
    ):
        qs = qs.filter(tipo=tipo)

    from regrarateio.convenio_imposto_rateio import gerar_rateio_impostos_total_convenio

    try:
        criados, lancados, ignorados = gerar_rateio_impostos_total_convenio(
            empresa_id=empresa_id,
            regra_id=regra_id,
            qs_filtro=qs,
            data_inicio=di,
            data_fim=df,
            periodo_ad_irpj=periodo_ad,
        )
        if lancados:
            msg = f'{criados} lançamento(s) gravado(s): {", ".join(lancados)}.'
            if ignorados:
                msg += f' Já existiam no mês (não duplicados): {", ".join(ignorados)}.'
            messages.success(request, msg)
    except Exception as exc:
        messages.error(request, f'Erro ao lançar impostos: {exc}')

    return redirect_lancamento_rateio_list(request, extra={'abrir_convenio': '1'})


def import_receita_planilha_modelo(request):
    from regrarateio.import_receita_planilha import gerar_modelo_receita_planilha_excel

    return gerar_modelo_receita_planilha_excel()


def _render_import_receita_preview(request, *, empresa_id, payload, regras, voltar_url):
    from regrarateio.import_receita_planilha import (
        PREVIEW_TABELA_MAX_LINHAS,
        carregar_chaves_importadas,
        resumo_previa_importacao,
    )

    linhas = payload.get('linhas') or []
    chaves = carregar_chaves_importadas(empresa_id)
    resumo = resumo_previa_importacao(empresa_id, linhas, chaves=chaves)
    tem_validas = any(ln.get('valido') for ln in linhas)
    total = len(linhas)
    ocultas = max(0, total - PREVIEW_TABELA_MAX_LINHAS)
    return render(
        request,
        'import_receita_planilha_preview.html',
        {
            'titulo': 'Prévia — importar receitas da planilha',
            'filename': payload.get('filename', ''),
            'linhas': linhas[:PREVIEW_TABELA_MAX_LINHAS],
            'linhas_ocultas': ocultas,
            'avisos': payload.get('avisos') or [],
            'erros': payload.get('erros') or [],
            'regras': regras,
            'voltar_url': voltar_url,
            'confirm_url': reverse_lazy('regrarateio:importReceitaPlanilha'),
            'total_linhas': total,
            'tem_linhas_validas': tem_validas,
            'resumo': resumo,
        },
    )


def import_receita_planilha(request):
    """Importa receitas de planilha Excel (exames) e gera rateio pela regra informada."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return redirect('empresa:lista')

    regras = RegraRateio.objects.filter(empresa_id=empresa_id, rateio='S').order_by('codigo', 'nomedaregra')
    voltar_url = reverse_lazy('regrarateio:lancamentoRateioList')

    if request.method == 'GET' and request.GET.get('preview') == '1':
        payload = request.session.get('rateio_import_preview')
        if not payload or payload.get('empresa_id') != empresa_id:
            messages.error(request, 'Prévia expirada. Envie a planilha novamente.')
            return redirect('regrarateio:importReceitaPlanilha')
        if not payload.get('linhas'):
            messages.error(request, 'Dados da importação não encontrados. Envie a planilha novamente.')
            return redirect('regrarateio:importReceitaPlanilha')
        return _render_import_receita_preview(
            request,
            empresa_id=empresa_id,
            payload=payload,
            regras=regras,
            voltar_url=voltar_url,
        )

    if request.method == 'POST' and request.POST.get('confirm_import') == '1':
        payload = request.session.get('rateio_import_preview')
        if not payload or payload.get('empresa_id') != empresa_id:
            messages.error(request, 'Prévia expirada. Envie a planilha novamente.')
            return redirect('regrarateio:importReceitaPlanilha')

        linhas = payload.get('linhas')
        if not linhas:
            messages.error(request, 'Dados da importação não encontrados. Envie a planilha novamente.')
            return redirect('regrarateio:importReceitaPlanilha')

        from regrarateio.import_receita_planilha import importar_receitas_planilha_lote

        offset = int(payload.get('offset') or 0)
        acum = payload.get('totais') or {
            'criados_car': 0,
            'criados_lr': 0,
            'ignorados': 0,
            'erros': [],
        }

        try:
            resultado = importar_receitas_planilha_lote(empresa_id, linhas, offset=offset)
        except Exception as exc:
            messages.error(request, f'Erro ao importar: {exc}')
            return redirect('regrarateio:importReceitaPlanilha')

        acum['criados_car'] += resultado['criados_car']
        acum['criados_lr'] += resultado['criados_lr']
        acum['ignorados'] += resultado['ignorados']
        acum['erros'].extend(resultado.get('erros') or [])

        if resultado.get('next_offset') is not None:
            payload['offset'] = resultado['next_offset']
            payload['totais'] = acum
            request.session['rateio_import_preview'] = payload
            request.session.modified = True
            pct = 0
            if resultado.get('total_validas'):
                pct = int(resultado['processadas_ate'] * 100 / resultado['total_validas'])
            return render(
                request,
                'import_receita_planilha_progress.html',
                {
                    'titulo': 'Importando planilha…',
                    'filename': payload.get('filename', ''),
                    'processadas_ate': resultado['processadas_ate'],
                    'total_validas': resultado['total_validas'],
                    'percentual': pct,
                    'confirm_url': reverse_lazy('regrarateio:importReceitaPlanilha'),
                },
            )

        if 'rateio_import_preview' in request.session:
            del request.session['rateio_import_preview']
            request.session.modified = True

        msg = (
            f"Importação concluída: {acum['criados_lr']} lançamento(s) de rateio "
            f"em {acum['criados_car']} título(s) a receber."
        )
        if acum['ignorados']:
            msg += f" Ignorados (duplicados/inválidos): {acum['ignorados']}."
        messages.success(request, msg)
        for err in acum['erros'][:10]:
            messages.warning(request, err)
        return redirect_lancamento_rateio_list(request)

    if request.method == 'POST':
        regra_raw = (request.POST.get('regra_padrao_id') or '').strip()
        arquivo = request.FILES.get('arquivo')
        regra_padrao_id = int(regra_raw) if regra_raw.isdigit() else None

        if not arquivo:
            messages.error(request, 'Selecione um arquivo Excel (.xlsx).')
            return redirect('regrarateio:importReceitaPlanilha')
        if not arquivo.name.lower().endswith(('.xlsx', '.xlsm')):
            messages.error(request, 'O arquivo deve ser .xlsx.')
            return redirect('regrarateio:importReceitaPlanilha')

        from regrarateio.import_receita_planilha import (
            parse_receita_planilha_xlsx,
            validar_linhas_importacao,
        )

        try:
            linhas, avisos = parse_receita_planilha_xlsx(
                arquivo.read(),
                regra_padrao_id=regra_padrao_id,
                empresa_id=empresa_id,
            )
        except Exception as exc:
            messages.error(request, f'Erro ao ler planilha: {exc}')
            return redirect('regrarateio:importReceitaPlanilha')

        if not linhas:
            for av in avisos[:8]:
                messages.warning(request, av)
            messages.error(request, 'Nenhuma linha válida para importar.')
            return redirect('regrarateio:importReceitaPlanilha')

        linhas, erros = validar_linhas_importacao(empresa_id, linhas)

        from regrarateio.import_receita_planilha import preparar_linhas_para_sessao

        request.session['rateio_import_preview'] = {
            'empresa_id': empresa_id,
            'filename': arquivo.name,
            'linhas': preparar_linhas_para_sessao(linhas),
            'avisos': avisos[:20],
            'erros': erros[:30],
            'offset': 0,
            'totais': None,
        }
        request.session.modified = True

        return redirect(reverse('regrarateio:importReceitaPlanilha') + '?preview=1')

    return render(
        request,
        'import_receita_planilha.html',
        {
            'titulo': 'Importar receitas — planilha Excel',
            'regras': regras,
            'voltar_url': voltar_url,
            'modelo_url': reverse_lazy('regrarateio:importReceitaPlanilhaModelo'),
        },
    )