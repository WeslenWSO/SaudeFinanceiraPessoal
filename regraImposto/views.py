from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import render
from django.db.models import Q
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage

from regraImposto.models import RegraImposto
from regraImposto.forms import RegraImpostoForm
from empresa.models import Empresa

class RegraImpostoList(ListView):
    model = RegraImposto
    template_name = "regra_List-Imposto.html"

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Regra Imposto'

        # Pagination
        page_size = self.request.GET.get('page_size', 10)
        try:
            page_size = int(page_size)
        except ValueError:
            page_size = 10
        if page_size not in [10, 20, 30, 50]:
            page_size = 10

        paginator = Paginator(context['object_list'], page_size)
        page = self.request.GET.get('page')
        try:
            regras = paginator.page(page)
        except PageNotAnInteger:
            regras = paginator.page(1)
        except EmptyPage:
            regras = paginator.page(paginator.num_pages)

        context['object_list'] = regras
        context['paginator'] = paginator
        context['page_obj'] = regras
        context['page_size'] = page_size
        context['page_sizes'] = [10, 20, 30, 50]

        return context

class RegraImpostoCreate(CreateView):
    model = RegraImposto
    form_class = RegraImpostoForm
    template_name = "regra_add-alterar.html"
    success_url = reverse_lazy('regraimposto:ListaRegra')

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Regra Imposto'
        context["titulo"] = 'Regra Imposto'
        return context

class RegraImpostoUpdate(UpdateView):
    model = RegraImposto
    form_class = RegraImpostoForm
    template_name = "regra_add-alterar.html"
    success_url = reverse_lazy('regraimposto:ListaRegra')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Regra Imposto'
        context["titulo"] = 'Regra Imposto'
        return context

class RegraImpostoDelete(DeleteView):
    model = RegraImposto
    success_url = reverse_lazy('regraimposto:ListaRegra')
    template_name = 'regra_confirm_delete.html'

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs