import os

from typing import Generic
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from socio.models import Socio
from empresa.models import Empresa
from django.core.paginator import Paginator
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.contrib import messages
from SaudeFinanceira import buscajson
from socio import views
import requests
import certifi

from django.conf.global_settings import MEDIA_ROOT
import shutil
from SaudeFinanceira import settings
from .forms import SocioForm
from django.views.generic import DetailView, ListView, UpdateView, DeleteView
session = requests.Session()
session.verify = certifi.where()


def listaSocio(request):
    print(request.POST)
    empresa_id = request.session.get('empresa_id')
    socios = Socio.objects.filter(empresa_id=empresa_id)
    # print(socios)
    #socios = Socio.objects.get(empresa_id=empresa_id)
    # cotacao = buscajson.cotacao(request)
    
    # paginator = Paginator(socios, 5)

    page = request.GET.get('p')
    # socios = paginator.get_page(page)
    return render(request, 'socioList.html', {
        'socios': socios,
        'titulo': 'Socio',
        'descricao': 'Lista de Socios'

        
    })

def Tela_Cad(request):
    #socios = Socio.objects.all()
    tipo = 0;

    soc = request.POST.get('inputFirstName')
    last = request.POST.get('inputLastName')
    # cotacao = buscajson.cotacao(request)
    empresa_id = request.session.get('empresa_id')
    empresa = None
    if empresa_id:
        try:
            empresa = Empresa.objects.get(id=empresa_id)
        except Empresa.DoesNotExist:
            empresa = None
    form = SocioForm()
    return render(request, 'socioAdd.html', {
     #   'socios': socios,
        'titulo': 'Socio',
        'descricao': 'Cadastrar Socio',
        'tipodealteracao': 'Adicionar',
        'tipo': tipo,
        'empresa': empresa,
        'form':form,
    })




def soc_CadTelEd(request, pk):
    
    # cotacao = buscajson.cotacao(request)
    tipo = 1;
    print(pk)
    socio = get_object_or_404(Socio, pk = pk)
    #socio = Socio.objects.get(pk=pk)
    request.session['Socio.pk'] = pk
    print(socio.avatarsoc)
    print(socio)
    form = SocioForm()
    context = {
        'socios': socio,
        'titulo': 'Socio',
        'descricao': 'Alterar Socio',
        'tipodealteracao': 'Alterando',
        'tipo': tipo,
        
        'form': form
        
    }
    return render(request, 'socioEdit.html', context)
def soc_Img(request, pk):
    # cotacao = buscajson.cotacao(request)
    tipo = 1;
    print(pk)
    socio = get_object_or_404(Socio, pk = pk)

    if request.method == 'POST':
        form = SocioForm(request.POST, request.FILES, instance=socio)
        if form.is_valid():
            form.save()
            messages.success(request, 'Imagem alterada com sucesso!')
            return redirect('socio:socList')
    else:
        form = SocioForm(instance=socio)

    context = {
        'socios': socio,
        'titulo': 'Socio',
        'descricao': 'Alterar Socio',
        'tipodealteracao': 'Alterando',
        'tipo': tipo,

        'form': form

    }
    return render(request, 'socioEditImg.html', context)

# class SocioUpdateView(UpdateView):
    
#       # specify the model you want to use
    
#     model = Socio
#     form_class = SocioForm
#     form = SocioForm()
#     template_name = "socioEdit.html"
    
#     #success_url = Socio.pk
#     def get_absolute_url(self):
#         return reverse('AltImg/', kwargs={'pk': self.pk})
    
    
    # form = SocioForm()
    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)
    #     if self.request.method == 'POST':
    #         form = SocioForm(self.request.POST, self.request.FILES)
    #         if form.is_valid():
    #                form.save()
    #         return redirect('soc_CadTelEd')
    #     else:
            
    #         messages.add_message(
    #         self.request,
    #         messages.ERROR,
    #         'Campo d não pode ficar vazio.'
    #        )
            
        
    #     tipo = 1;    
    #     context["socios"] = get_object_or_404(Socio, pk=Socio.pk)
    #     context["cotacao"] = cotacao = buscajson.cotacao(self.request)
    #     context["form"] = form
    #     return context
    
    
        
        
       
            
    
    
    
    
    
    
    
    
def soc_Cad(request):
    # cotacao = buscajson.cotacao(request)
    soc = request.POST.get('inputFirstName')
    #soc = request.POST.get('socio')
    last = request.POST.get('inputLastName')
    email =request.POST.get('email')
    tipo = request.POST.get('selTipo')
    empresa_id = request.session.get('empresa_id')
    print(soc)

    if not soc:
        messages.error(request, 'Nenhum campo pode estar vazio.')
        return render(request, 'socioList.html'

                )

    socio = Socio.objects.create(socio=soc, lastname=last, email=email, tipo=tipo, empresa_id=empresa_id)  #Empresa(razao=razao, cnpj=cnpj, telefone=telefone)

    # Handle photo upload
    if request.FILES.get('avatarsoc'):
        socio.avatarsoc = request.FILES['avatarsoc']
        socio.save()

    socio.save()

    messages.success(request, 'Registrado com sucesso! Agora faça login.')
    return redirect('socio:socList')

def soc_Cad_Alt(request):

    id = request.POST.get('id')
    print(id)
    socio = request.POST.get('inputFirstName')
    last = request.POST.get("inputLastName")
    email = request.POST.get("email", None)
    tipo = request.POST.get("selTipo", None)

    soc = get_object_or_404(Socio, id=id)
    print(socio)
    print(email)
    print(last)
    print(tipo)

    soc.socio = socio
    soc.email = email
    soc.lastname = last
    soc.tipo = tipo

    # Handle photo upload
    if request.FILES.get('avatarsoc'):
        soc.avatarsoc = request.FILES['avatarsoc']

    soc.save()
    messages.success(request, 'Alterado com sucesso! ')
    return redirect('socio:socList')

def soc_CadExcluir(request, soc_id):


    try:
        socio = Socio.objects.get(id=soc_id)
        print('alert(Hello! I am an alert box!! )')
        socio.delete()
        print("Record deleted successfully!")
        messages.success(request, 'Exluido com sucesso! ')
    except:
        print("Record doesn't exists")
        messages.success(request,"Record doesn't exists")

    messages.success(request, 'Exluido com sucesso! ')
    return redirect('socio:socList')