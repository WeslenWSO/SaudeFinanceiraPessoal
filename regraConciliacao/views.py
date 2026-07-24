from typing import Any
from django.db import models
from django.db.models.query import QuerySet
from django.urls import reverse_lazy
from django.utils import timezone
from django.shortcuts import render, redirect
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView, DeleteView
from django.contrib import messages
from django.views.generic.edit import CreateView
from regraConciliacao.models import RegraConciliacao
from regraConciliacao.forms import RegraConciliacaoForm
from categoria.models import Categoria
from fornecedor.models import Fornecedor
from cliente.models import Cliente
from empresa.models import Empresa
from extrato.models import Banco, ContaBancaria

class RegraConciliacaoList(ListView):
    model = RegraConciliacao
    paginate_by = 10
    template_name = "regra_list.html"

    def get_paginate_by(self, queryset):
        return self.request.GET.get('paginate_by', 50)

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        # Filtros de busca
        search_query = self.request.GET.get('search', '')
        if search_query:
            qs = qs.filter(
                models.Q(categoria__nome__icontains=search_query) |
                models.Q(forma_pagamento__descricao__icontains=search_query) |
                models.Q(fornecedor__razao__icontains=search_query) |
                models.Q(definicao_historico__icontains=search_query)
            )

        qs = qs.order_by("-data_criacao")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Regras de Conciliação'
        context["now"] = timezone.now()
        return context

class RegraConciliacaoUpdate(UpdateView):
    model = RegraConciliacao
    form_class = RegraConciliacaoForm
    template_name = "regra_add_alterar.html"
    success_url = reverse_lazy('regraConciliacao:regraList')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa_id'] = self.request.session.get('empresa_id')
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Regra atualizada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Regra de Conciliação'
        context["titulo"] = 'Regra de Conciliação'
        return context

class RegraConciliacaoCreate(CreateView):
    model = RegraConciliacao
    form_class = RegraConciliacaoForm
    template_name = "regra_add_alterar.html"
    success_url = reverse_lazy('regraConciliacao:regraList')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa_id'] = self.request.session.get('empresa_id')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Regra de Conciliação'
        context["titulo"] = 'Regra de Conciliação'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if not empresa_id:
            messages.error(self.request, "Nenhuma empresa selecionada na sessão. Selecione uma empresa e tente novamente.")
            return self.form_invalid(form)
        form.instance.empresa_id = empresa_id
        messages.success(self.request, "Regra criada com sucesso.")
        return super().form_valid(form)

class RegraConciliacaoDelete(DeleteView):
    model = RegraConciliacao
    success_url = reverse_lazy('regraConciliacao:regraList')
    template_name = 'regra_confirm_delete.html'

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Regra excluída com sucesso.")
        return super().delete(request, *args, **kwargs)
