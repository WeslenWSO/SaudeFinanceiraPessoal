from typing import Any
import json

from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models.query import QuerySet
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods
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

    SORT_FIELDS = {
        'id': 'id',
        'nome': 'nome',
        'classificacao': 'classificacao',
        'grupo': 'grupo',
        'tipo': 'tipo',
        'sintetico': 'sintetico',
        'conta_azul': 'conta_azul_id',
    }

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
                models.Q(classificacao__icontains=search_query) |
                models.Q(grupo__icontains=search_query)
            )

        order = (self.request.GET.get('order') or 'classificacao').strip().lower()
        direction = (self.request.GET.get('dir') or 'asc').strip().lower()
        field = self.SORT_FIELDS.get(order, 'classificacao')
        if direction == 'desc':
            field = f'-{field}'
        qs = qs.order_by(field, 'id')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Categoria'
        context["now"] = timezone.now()
        order = (self.request.GET.get('order') or 'classificacao').strip().lower()
        direction = (self.request.GET.get('dir') or 'asc').strip().lower()
        if order not in self.SORT_FIELDS:
            order = 'classificacao'
        if direction not in ('asc', 'desc'):
            direction = 'asc'
        context['order'] = order
        context['dir'] = direction
        context['search'] = self.request.GET.get('search', '')
        context['paginate_by'] = self.request.GET.get('paginate_by', '50')
        context['colunas'] = [
            ('id', 'ID'),
            ('nome', 'Nome'),
            ('classificacao', 'Classificação'),
            ('grupo', 'Grupo'),
            ('conta_azul', 'Conta Azul'),
            ('tipo', 'Tipo'),
            ('sintetico', 'Sintético'),
        ]
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
        messages.success(self.request, "Categoria atualizada com sucesso.")
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
        messages.success(self.request, "Categoria criada com sucesso.")
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


def _copiar_categorias(destino: Empresa, origem_qs) -> tuple[int, int]:
    """Copia categorias para a empresa destino. Retorna (criadas, ignoradas)."""
    criadas = 0
    ignoradas = 0
    for cat in origem_qs.iterator():
        existe = Categoria.objects.filter(
            empresa=destino,
            nome__iexact=cat.nome,
            tipo=cat.tipo,
            classificacao__iexact=cat.classificacao or '',
        ).exists()
        if existe:
            ignoradas += 1
            continue
        Categoria.objects.create(
            empresa=destino,
            nome=cat.nome,
            grupo=cat.grupo,
            classificacao=cat.classificacao or '',
            sintetico=cat.sintetico or 'A',
            tipo=cat.tipo or 'D',
            bloquear_sync_conta_azul=bool(cat.bloquear_sync_conta_azul),
            conta_azul_id='',
        )
        criadas += 1
    return criadas, ignoradas


@login_required
@require_GET
def grupos_empresa(request):
    """JSON: grupos de categorias de uma empresa (para o select de cópia)."""
    empresa_id = request.GET.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'grupos': []})
    qs = (
        Categoria.objects.filter(empresa_id=empresa_id)
        .exclude(grupo__isnull=True)
        .exclude(grupo='')
        .values('grupo')
        .annotate(qtd=models.Count('id'))
        .order_by('grupo')
    )
    grupos = [{'nome': row['grupo'], 'qtd': row['qtd']} for row in qs]
    # Inclui "Sem grupo" se houver categorias sem grupo
    sem_grupo = Categoria.objects.filter(empresa_id=empresa_id).filter(
        models.Q(grupo__isnull=True) | models.Q(grupo=''),
    ).count()
    if sem_grupo:
        grupos.append({'nome': '__SEM_GRUPO__', 'qtd': sem_grupo, 'rotulo': 'Sem grupo'})
    return JsonResponse({'grupos': grupos})


@login_required
@require_http_methods(['GET', 'POST'])
def copiar_categorias(request):
    """Copia categorias de outra empresa (todas ou por grupo) para a empresa da sessão."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa na sessão.')
        return redirect('empresa:lista')

    destino = get_object_or_404(Empresa, pk=empresa_id)
    empresas_origem = Empresa.objects.exclude(pk=destino.pk).order_by('razao')
    modo = (request.POST.get('modo') or request.GET.get('modo') or 'todas').strip()
    grupo_sel = (request.POST.get('grupo') or request.GET.get('grupo') or '').strip()
    origem_id = (request.POST.get('empresa_origem') or request.GET.get('empresa_origem') or '').strip()

    if request.method == 'POST':
        if not origem_id:
            messages.error(request, 'Selecione a empresa de origem.')
            return redirect('categoria:copiar')
        if str(origem_id) == str(destino.pk):
            messages.error(request, 'A empresa de origem deve ser diferente da atual.')
            return redirect('categoria:copiar')

        origem = get_object_or_404(Empresa, pk=origem_id)
        qs = Categoria.objects.filter(empresa=origem)

        if modo == 'grupo':
            if not grupo_sel:
                messages.error(request, 'Selecione o grupo a copiar.')
                return redirect('categoria:copiar')
            if grupo_sel == '__SEM_GRUPO__':
                qs = qs.filter(models.Q(grupo__isnull=True) | models.Q(grupo=''))
                rotulo = 'sem grupo'
            else:
                qs = qs.filter(grupo=grupo_sel)
                rotulo = grupo_sel
        else:
            rotulo = 'todas'

        total_origem = qs.count()
        if total_origem == 0:
            messages.warning(request, 'Nenhuma categoria encontrada na origem com esse filtro.')
            return redirect('categoria:copiar')

        criadas, ignoradas = _copiar_categorias(destino, qs)
        messages.success(
            request,
            f'Cópia concluída ({rotulo}) de {origem.razao}: '
            f'{criadas} criada(s), {ignoradas} já existia(m) e foi(ram) ignorada(s). '
            f'Origem: {total_origem} categoria(s).',
        )
        return redirect('categoria:catList')

    return render(request, 'cat-copiar.html', {
        'empresa_destino': destino,
        'empresas_origem': empresas_origem,
        'modo': modo,
        'empresa_origem_id': origem_id,
        'grupo_selecionado_json': json.dumps(grupo_sel, ensure_ascii=False),
        'descricao': 'Copiar categorias',
    })