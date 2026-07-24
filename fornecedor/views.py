import json
import re
from typing import Any
from django.db import transaction
from django.db.models import Count
from django.db.models.query import QuerySet
from django.urls import reverse_lazy
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView
from django.contrib import messages
from django.views.generic.edit import CreateView
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from fornecedor.models import Fornecedor, SocioFornecedor
from fornecedor.forms import FornecedorForm
from empresa.models import Empresa
from contasapagar.models import ContasaPagar
from regraConciliacao.models import RegraConciliacao

# Create your views here.


def _salvar_socios_fornecedor(fornecedor, raw_json):
    """
    Persiste sócios a partir de JSON (lista de {nome, tipo} ou {socio, qualificacao}).
    Lista vazia ou ausente remove sócios e não exige nenhum cadastro.
    """
    SocioFornecedor.objects.filter(fornecedor=fornecedor).delete()
    if not (raw_json or "").strip():
        return
    try:
        arr = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(arr, list) or len(arr) == 0:
        return
    criar = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        nome = (item.get("nome") or item.get("socio") or "").strip()
        if not nome:
            continue
        tipo = (item.get("tipo") or item.get("qualificacao") or "Sócio").strip()[:100] or "Sócio"
        criar.append(
            SocioFornecedor(
                fornecedor=fornecedor,
                nome=nome[:200],
                tipo_qualificacao=tipo,
            )
        )
    if criar:
        SocioFornecedor.objects.bulk_create(criar)


class FornList(ListView):
    model = Fornecedor
    paginate_by = 10  # if pagination is desired
    template_name = "forn-List.html"


    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.annotate(socios_count=Count("socios", distinct=True)).order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Fornecedor'
        context["now"] = timezone.now()
        return context
    
class FornUpdate(UpdateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "forn-add-alterar.html"

    # fields = [
    #     "descricao",
    #     "tipo"
    # ]

    success_url = reverse_lazy('fornecedor:fornList')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        raw_socios = (self.request.POST.get("socios_json") or "").strip()
        with transaction.atomic():
            response = super(FornUpdate, self).form_valid(form)
            _salvar_socios_fornecedor(form.instance, raw_socios)
        messages.success(self.request, "Fornecedor atualizado com sucesso.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Fornecedor'
        context["titulo"] = 'Fornecedor'
        obj = self.object
        if obj and obj.pk:
            socios = [
                {"nome": s.nome, "tipo": s.tipo_qualificacao}
                for s in obj.socios.all()
            ]
            context["socios_json_initial"] = json.dumps(socios, ensure_ascii=False)
        else:
            context["socios_json_initial"] = "[]"

        return context
    
    
    
class FornCreate(CreateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name= "forn-add-alterar.html"


    #fields = ['title','description','completed']
    success_url = reverse_lazy('fornecedor:fornList')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        rz = (self.request.GET.get('razao') or '').strip()
        cj = (self.request.GET.get('cnpj') or '').strip()
        tf = (self.request.GET.get('telefone') or '').strip()
        if rz:
            initial['razao'] = rz[:50]
        if cj:
            initial['cnpj'] = cj[:20]
        if tf:
            digitos = re.sub(r'\D', '', tf)[:11]
            if digitos:
                initial['telefone'] = digitos
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Fornecedor'
        context["titulo"] = 'Fornecedor'
        context.setdefault("socios_json_initial", "[]")
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        raw_socios = (self.request.POST.get("socios_json") or "").strip()
        with transaction.atomic():
            response = super(FornCreate, self).form_valid(form)
            _salvar_socios_fornecedor(form.instance, raw_socios)
        messages.success(self.request, "Fornecedor criado com sucesso.")
        return response


@login_required
@require_POST
def excluir_fornecedor(request, pk):
    """Exclui fornecedor do cadastro da empresa atual, se não houver vínculos."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('fornecedor:fornList')

    fornecedor = get_object_or_404(Fornecedor, pk=pk, empresa_id=empresa_id)
    razao = fornecedor.razao

    # Evita import circular no carregamento do módulo
    from notafiscalentrada.views import _fornecedor_ainda_referenciado_em_notas_entrada

    if _fornecedor_ainda_referenciado_em_notas_entrada(fornecedor, empresa_id):
        messages.error(
            request,
            'Não é possível excluir: há notas fiscais de entrada vinculadas a este fornecedor.',
        )
        return redirect('fornecedor:fornList')

    if ContasaPagar.objects.filter(fornecedor=fornecedor).exists():
        messages.error(
            request,
            'Não é possível excluir: existem contas a pagar vinculadas a este fornecedor.',
        )
        return redirect('fornecedor:fornList')

    if RegraConciliacao.objects.filter(fornecedor=fornecedor).exists():
        messages.error(
            request,
            'Não é possível excluir: este fornecedor está em regra(s) de conciliação.',
        )
        return redirect('fornecedor:fornList')

    fornecedor.delete()
    messages.success(request, 'Fornecedor "%s" excluído com sucesso.' % razao)
    return redirect('fornecedor:fornList')