from typing import Any
from django.db.models.query import QuerySet
from django.urls import reverse_lazy
from django.utils import timezone
from django.shortcuts import render, redirect
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView
from django.contrib import messages
from django.views.generic.edit import CreateView
from cliente.models import Cliente
from cliente.forms import ClienteForm
from empresa.models import Empresa
from django.views.generic import DeleteView

# Create your views here.
class ClieDelete(DeleteView):
    model = Cliente
    success_url = reverse_lazy('cliente:clieList')
    template_name = 'cliente_confirm_delete.html'

class ClieList(ListView):
    model = Cliente
    paginate_by = 10  # if pagination is desired
    template_name = "cliente-List.html"


    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Cliente'
        context["now"] = timezone.now()
        return context
class ClieUpdate(UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name= "cliente-add-alterar.html"

    # fields = [
    #     "descricao",
    #     "tipo"
    # ]

    success_url = reverse_lazy('cliente:clieList')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "The task was updated successfully.")
        return super(ClieUpdate,self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Cliente'
        context["titulo"] = 'Cliente'

        return context
    
    
    
class ClieCreate(CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name= "cliente-add-alterar.html"


    #fields = ['title','description','completed']
    success_url = reverse_lazy('cliente:clieList')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Cliente'
        context["titulo"] = 'Cliente'

        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "The task was created successfully.")
        return super(ClieCreate,self).form_valid(form)