from django.urls import reverse_lazy
from django.utils import timezone
from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.edit import UpdateView, CreateView
from django.contrib import messages
from django.db.models import Q
from .models import Convenio, ServicosMedicos, TabelaPreco, Cabecalho
from .forms import ConvenioForm, ServicosMedicosForm, TabelaPrecoForm
from empresa.models import Empresa

# Convenio Views
class ConvenioList(ListView):
    model = Convenio
    paginate_by = 10
    template_name = "servicos_medicos/convenio_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Convênios'
        context["now"] = timezone.now()
        return context

class ConvenioCreate(CreateView):
    model = Convenio
    form_class = ConvenioForm
    template_name = "servicos_medicos/convenio_form.html"
    success_url = reverse_lazy('servicos_medicos:convenio_list')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Convênio'
        context["titulo"] = 'Convênio'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        messages.success(self.request, "Convênio criado com sucesso.")
        return super().form_valid(form)

class ConvenioUpdate(UpdateView):
    model = Convenio
    form_class = ConvenioForm
    template_name = "servicos_medicos/convenio_form.html"
    success_url = reverse_lazy('servicos_medicos:convenio_list')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "Convênio atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Convênio'
        context["titulo"] = 'Convênio'
        return context

# ServicosMedicos Views
class ServicosMedicosList(ListView):
    model = ServicosMedicos
    paginate_by = 10
    template_name = "servicos_medicos/servicos_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        search_query = self.request.GET.get('q', '')
        if search_query:
            qs = qs.filter(
                Q(codigo__icontains=search_query) |
                Q(servicos__icontains=search_query)
            )
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Serviços Médicos'
        context["now"] = timezone.now()
        return context

class ServicosMedicosCreate(CreateView):
    model = ServicosMedicos
    form_class = ServicosMedicosForm
    template_name = "servicos_medicos/servicos_form.html"
    success_url = reverse_lazy('servicos_medicos:servicos_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Serviço Médico'
        context["titulo"] = 'Serviço Médico'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Serviço Médico criado com sucesso.")
        return super().form_valid(form)

class ServicosMedicosUpdate(UpdateView):
    model = ServicosMedicos
    form_class = ServicosMedicosForm
    template_name = "servicos_medicos/servicos_form.html"
    success_url = reverse_lazy('servicos_medicos:servicos_list')

    def form_valid(self, form):
        messages.success(self.request, "Serviço Médico atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Serviço Médico'
        context["titulo"] = 'Serviço Médico'
        return context

# TabelaPreco Views
class TabelaPrecoList(ListView):
    model = TabelaPreco
    paginate_by = 25
    template_name = "servicos_medicos/tabela_list.html"
    PAGINATE_OPTIONS = (10, 25, 50, 100, 200)

    def get_paginate_by(self, queryset):
        raw = self.request.GET.get('per_page') or self.request.GET.get('paginate_by')
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self.paginate_by
        if value in self.PAGINATE_OPTIONS:
            return value
        return self.paginate_by

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        cabecalho_id = self.request.GET.get('cabecalho_id')
        if cabecalho_id:
            qs = qs.filter(cabecalho_id=cabecalho_id)
        qs = qs.select_related('empresa', 'convenio', 'cabecalho', 'codigo_servico').order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Tabela de Preços'
        context["now"] = timezone.now()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            context["cabecalhos"] = Cabecalho.objects.filter(empresa_id=empresa_id)
        else:
            context["cabecalhos"] = Cabecalho.objects.none()
        context["cabecalho_selecionado"] = self.request.GET.get('cabecalho_id', '')
        context["per_page"] = str(self.get_paginate_by(self.object_list))
        context["paginate_options"] = self.PAGINATE_OPTIONS
        return context

class TabelaPrecoCreate(CreateView):
    model = TabelaPreco
    form_class = TabelaPrecoForm
    template_name = "servicos_medicos/tabela_form.html"
    success_url = reverse_lazy('servicos_medicos:tabela_list')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Tabela de Preço'
        context["titulo"] = 'Tabela de Preço'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        messages.success(self.request, "Tabela de Preço criada com sucesso.")
        return super().form_valid(form)

class TabelaPrecoUpdate(UpdateView):
    model = TabelaPreco
    form_class = TabelaPrecoForm
    template_name = "servicos_medicos/tabela_form.html"
    success_url = reverse_lazy('servicos_medicos:tabela_list')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "Tabela de Preço atualizada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Tabela de Preço'
        context["titulo"] = 'Tabela de Preço'
        return context

# Cabecalho Views
class CabecalhoList(ListView):
    model = Cabecalho
    paginate_by = 10
    template_name = "servicos_medicos/cabecalho_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Cabeçalhos'
        context["now"] = timezone.now()
        return context

class CabecalhoCreate(CreateView):
    model = Cabecalho
    fields = ['empresa', 'convenio', 'nome_tabela']
    template_name = "servicos_medicos/cabecalho_form.html"
    success_url = reverse_lazy('servicos_medicos:cabecalho_list')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Cabeçalho'
        context["titulo"] = 'Cabeçalho'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        messages.success(self.request, "Cabeçalho criado com sucesso.")
        return super().form_valid(form)

class CabecalhoUpdate(UpdateView):
    model = Cabecalho
    fields = ['empresa', 'convenio', 'nome_tabela']
    template_name = "servicos_medicos/cabecalho_form.html"
    success_url = reverse_lazy('servicos_medicos:cabecalho_list')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "Cabeçalho atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Cabeçalho'
        context["titulo"] = 'Cabeçalho'
        return context
