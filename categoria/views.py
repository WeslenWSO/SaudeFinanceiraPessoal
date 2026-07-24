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
from categoria.models import Categoria
from categoria.forms import CategoriaForm
from empresa.models import Empresa

# Create your views here.

class CatList(ListView):
    model = Categoria
    paginate_by = 10  # if pagination is desired
    template_name = "cat-List.html"

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
                models.Q(nome__icontains=search_query) |
                models.Q(classificacao__icontains=search_query)
            )

        qs = qs.order_by("classificacao")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Categoria'
        context["now"] = timezone.now()
        return context
    
class CatUpdate(UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "cat-add-alterar.html"

    # fields = [
    #     "descricao",
    #     "tipo"
    # ]

    success_url = reverse_lazy('categoria:catList')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "The task was updated successfully.")
        return super(CatUpdate,self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Categoria'
        context["titulo"] = 'Categoria'

        return context
    
    
    
class CatCreate(CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name= "cat-add-alterar.html"


    #fields = ['title','description','completed']
    success_url = reverse_lazy('categoria:catList')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Categoria'
        context["titulo"] = 'Categoria'

        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "The task was created successfully.")
        return super(CatCreate,self).form_valid(form)


class CatDelete(DeleteView):
    model = Categoria
    success_url = reverse_lazy('categoria:catList')
    template_name = 'cat_confirm_delete.html'  # Você pode criar um template de confirmação

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Categoria excluída com sucesso.")
        return super().delete(request, *args, **kwargs)