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
from cobranca.models import Cobranca



# Create your views here.


class CobList(ListView):
    model = Cobranca
    paginate_by = 10  # if pagination is desired
    template_name = "cob-List.html"
    
    
    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista Cobranca'
        context["now"] = timezone.now()
        return context
    
# class CobDetail(DetailView):
#     model = Cobranca
#     template_name = "forma-detail.html"
    
#     def get_context_data(self, **kwargs):
#         context = super(CobDetail, self).get_context_data(**kwargs)
#         context["now"] = timezone.now()
#         context["descricao"] = 'Detalhes de Forma de Pagto'
#         return context

class CobUpdate(UpdateView):
    model = Cobranca
    fields = "__all__"
    template_name= "cob-Add_Alterar.html"
    
    # fields = [
    #     "descricao",
    #     "tipo"
    # ]
  
    success_url = reverse_lazy('cobranca:cobList')
    def form_valid(self, form):
        messages.success(self.request, "The task was updated successfully.")
        return super(CobUpdate,self).form_valid(form)
     
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Cobranca'
        context["titulo"] = 'Cobranca'
        
        return context


class CobCreate(CreateView):
    model = Cobranca
    fields = "__all__" 
    template_name= "cob-Add_Alterar.html"
    
     
    #fields = ['title','description','completed']
    success_url = reverse_lazy('cobranca:cobList')
   
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Cobranca'
        context["titulo"] = 'Cobranca'
        
        return context
   
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "The task was created successfully.")
        return super(CobCreate,self).form_valid(form)  