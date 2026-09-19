from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic.list import ListView

from estoque.forms import ProdutoEstoqueForm
from estoque.models import ProdutoEstoque


class _EmpresaQuerysetMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs


class ProdutoEstoqueListView(LoginRequiredMixin, _EmpresaQuerysetMixin, ListView):
    model = ProdutoEstoque
    paginate_by = 25
    template_name = 'estoque/produto_list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(codigo_produto__icontains=q)
                | Q(descricao__icontains=q)
                | Q(marca__icontains=q)
            )
        return qs.order_by('codigo_produto', 'descricao')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Estoque — produtos'
        ctx['busca'] = (self.request.GET.get('q') or '').strip()
        ctx['now'] = timezone.now()
        return ctx


class ProdutoEstoqueCreateView(LoginRequiredMixin, CreateView):
    model = ProdutoEstoque
    form_class = ProdutoEstoqueForm
    template_name = 'estoque/produto_form.html'
    success_url = reverse_lazy('estoque:produto_list')

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if not empresa_id:
            messages.error(self.request, 'Selecione uma empresa antes de cadastrar produtos.')
            return redirect('empresa:lista')
        form.instance.empresa_id = empresa_id
        messages.success(self.request, 'Produto cadastrado com sucesso.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Novo produto — estoque'
        return ctx


class ProdutoEstoqueUpdateView(LoginRequiredMixin, _EmpresaQuerysetMixin, UpdateView):
    model = ProdutoEstoque
    form_class = ProdutoEstoqueForm
    template_name = 'estoque/produto_form.html'
    success_url = reverse_lazy('estoque:produto_list')

    def form_valid(self, form):
        messages.success(self.request, 'Produto atualizado com sucesso.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Editar produto — estoque'
        return ctx


@login_required
@require_POST
def excluir_produto_estoque(request, pk):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:produto_list')

    produto = get_object_or_404(ProdutoEstoque, pk=pk, empresa_id=empresa_id)
    produto.delete()
    messages.success(request, 'Produto excluído.')
    return redirect('estoque:produto_list')
