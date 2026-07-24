import decimal
from multiprocessing import context
from typing import Any
from django.db.models.query import QuerySet
from django.urls import reverse_lazy
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
    gerar_rateio_contas_pagar,
    gerar_rateio_contas_receber,
    query_contas_pagar_rateio_candidatas,
    query_contas_receber_rateio_candidatas,
    reaplicar_regra_no_titulo,
    valor_base_titulo_de_lancamento,
    preview_linhas_rateio_por_regra,
)
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.dateparse import parse_date
from decimal import Decimal

from django.db.models import Count, Min, Q, Sum
from socio.models import Socio
from .forms import FormRecalcularRateioGrupo, FormRegraItem, FormRegraRateio


class RegraCreate(CreateView):
    model = RegraRateio
    fields = ['codigo', 'nomedaregra', 'rateio']
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
        
        if nomeregra.rateio == 'N':
            pass
        else:
         for i in RegraRateioItem.objects.filter(regrarateio=nomeregra):
          context["tot"] = RegraRateioItem.objects.filter(regrarateio=nomeregra).aggregate(Sum('percRateio'))
          
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
    fields = ['codigo', 'nomedaregra', 'rateio']
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

    def get_queryset(self):
        qs = LancamentoRateio.objects.select_related(
            'regra_rateio',
            'socio',
            'conta_pagar',
            'conta_pagar__categoria',
            'conta_pagar__cobranca',
            'conta_receber',
            'conta_receber__nota',
            'conta_receber__forma_pagamento',
        )
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        di = parse_date((self.request.GET.get('data_inicio') or '').strip() or '')
        df = parse_date((self.request.GET.get('data_fim') or '').strip() or '')
        qs = _filtra_queryset_lancamento_rateio_por_periodo(qs, di, df)

        socio_raw = (self.request.GET.get('socio') or '').strip()
        if socio_raw.isdigit():
            qs = qs.filter(socio_id=int(socio_raw))

        tipo = (self.request.GET.get('tipo') or '').strip()
        if tipo in (LancamentoRateio.TIPO_PGTO, LancamentoRateio.TIPO_RECEBIMENTO):
            qs = qs.filter(tipo=tipo)

        return qs.order_by('-data_pagamento', '-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa_id = self.request.session.get('empresa_id')
        from socio.models import Socio

        context['socios'] = (
            Socio.objects.filter(empresa_id=empresa_id).order_by('socio', 'lastname')
            if empresa_id
            else Socio.objects.none()
        )
        context['filtro_data_inicio'] = (self.request.GET.get('data_inicio') or '').strip()
        context['filtro_data_fim'] = (self.request.GET.get('data_fim') or '').strip()
        socio_get = (self.request.GET.get('socio') or '').strip()
        context['filtro_socio'] = socio_get
        context['filtro_socio_id'] = int(socio_get) if socio_get.isdigit() else None
        context['filtro_tipo'] = (self.request.GET.get('tipo') or '').strip()
        context['tipo_choices'] = LancamentoRateio.TIPO_CHOICES
        q = self.request.GET.copy()
        q.pop('page', None)
        context['filter_query'] = q.urlencode()
        context['regras_rateio_modal'] = (
            RegraRateio.objects.filter(empresa_id=empresa_id).order_by('nomedaregra')
            if empresa_id
            else RegraRateio.objects.none()
        )

        # Totais do conjunto filtrado (todas as páginas), não só da página atual
        qs_filtro = self.get_queryset()
        agg = qs_filtro.aggregate(
            total_qtd=Count('id'),
            total_valor=Sum('valor'),
        )
        tot_pg = qs_filtro.filter(tipo=LancamentoRateio.TIPO_PGTO).aggregate(s=Sum('valor'))
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

        # Cards por sócio: soma PGTO para exibir "Valor pago" (recebimento só entra para listar sócios extras com movimento).
        raw_pg = {}
        raw_rec = {}
        for sid, tipo, valor in qs_filtro.values_list('socio_id', 'tipo', 'valor'):
            if sid is None:
                continue
            v = _to_dec(valor)
            if tipo == LancamentoRateio.TIPO_PGTO:
                raw_pg[sid] = raw_pg.get(sid, Decimal('0')) + v
            elif tipo == LancamentoRateio.TIPO_RECEBIMENTO:
                raw_rec[sid] = raw_rec.get(sid, Decimal('0')) + v

        def _card_socio_dict(nome, extra, pg):
            pg_abs = abs(pg)
            return {
                'nome': nome,
                'extra': extra,
                'pgto_abs_txt': _fmt_br_moeda(pg_abs),
            }

        ids_empresa = {s.id for s in context['socios']}
        sids_com_movimento = set(raw_pg) | set(raw_rec)
        cards_socios = []
        for s in context['socios']:
            pg = raw_pg.get(s.id, Decimal('0'))
            cards_socios.append(_card_socio_dict(str(s), False, pg))
        extras_ids = sorted(sids_com_movimento - ids_empresa)
        for sid in extras_ids:
            pg = raw_pg.get(sid, Decimal('0'))
            try:
                s_obj = Socio.objects.get(pk=sid)
                nome = str(s_obj)
            except Socio.DoesNotExist:
                nome = f'Sócio #{sid} (cadastro não encontrado)'
            cards_socios.append(_card_socio_dict(nome, True, pg))
        context['cards_socios'] = cards_socios

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
        out[str(r.pk)] = [
            {'socio_id': i.socios_id, 'nome': str(i.socios), 'perc': str(i.percRateio or 0)}
            for i in itens
        ]
    return json.dumps(out, ensure_ascii=False)


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
            initial={'regra_rateio': regra_atual.pk if regra_atual else None},
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
                n, = reaplicar_regra_no_titulo(lanc.pk, nova.pk)
                messages.success(
                    request,
                    f'Rateio atualizado: {n} linha(s) gravada(s) conforme a regra «{nova}».',
                )
                return redirect('regrarateio:lancamentoRateioList')
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
        return redirect('regrarateio:lancamentoRateioList')

    context = {
        'lancamento': lancamento,
        'titulo': 'Excluir lançamento de rateio',
        'descricao': (
            f'Confirma a exclusão deste lançamento? '
            f'{lancamento.get_tipo_display()} — {lancamento.socio} — valor {lancamento.valor}'
        ),
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

    try:
        contas = query_contas_pagar_rateio_candidatas(empresa_id, di, df)
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
        return redirect('regrarateio:lancamentoRateioList')

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('regrarateio:lancamentoRateioList')

    raw_ids = request.POST.getlist('conta_pagar_id')
    ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]

    if not ids:
        messages.error(request, 'Selecione ao menos uma conta a pagar.')
        return redirect('regrarateio:lancamentoRateioList')

    rid = (request.POST.get('regra_rateio') or '').strip()
    regra_id_forcar = int(rid) if rid.isdigit() else None

    try:
        criados, ignorados = gerar_rateio_contas_pagar(
            empresa_id=empresa_id,
            conta_pagar_ids=ids,
            regra_id_forcar=regra_id_forcar,
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

    return redirect('regrarateio:lancamentoRateioList')


def gerar_rateio_contas_receber_aplicar(request):
    """POST: aplica regra nas contas a receber selecionadas no modal (valores positivos no rateio)."""
    if request.method != 'POST':
        return redirect('regrarateio:lancamentoRateioList')

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('regrarateio:lancamentoRateioList')

    raw_ids = request.POST.getlist('conta_receber_id')
    ids = [int(x) for x in raw_ids if str(x).strip().isdigit()]

    if not ids:
        messages.error(request, 'Selecione ao menos uma conta a receber.')
        return redirect('regrarateio:lancamentoRateioList')

    rid = (request.POST.get('regra_rateio') or '').strip()
    regra_id_forcar = int(rid) if rid.isdigit() else None

    try:
        criados, ignorados = gerar_rateio_contas_receber(
            empresa_id=empresa_id,
            conta_receber_ids=ids,
            regra_id_forcar=regra_id_forcar,
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

    return redirect('regrarateio:lancamentoRateioList')