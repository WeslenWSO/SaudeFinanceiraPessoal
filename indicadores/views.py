from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from .forms import IndicadorForm
from .models import Indicador, garantir_indicadores_padrao


class IndicadorList(ListView):
    model = Indicador
    template_name = 'indicadores/listar.html'

    def dispatch(self, request, *args, **kwargs):
        empresa_id = request.session.get('empresa_id')
        if not empresa_id:
            messages.error(request, 'Selecione uma empresa.')
            return redirect('empresa:trocar')
        garantir_indicadores_padrao(empresa_id)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs.order_by('area', 'ordem', 'nome')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Cadastro de Indicadores'
        context['now'] = timezone.now()
        por_area = {codigo: [] for codigo, _ in Indicador.AREA_CHOICES}
        for item in context['object_list']:
            por_area.setdefault(item.area, []).append(item)
        context['areas'] = [
            {
                'codigo': codigo,
                'rotulo': rotulo,
                'itens': por_area.get(codigo, []),
            }
            for codigo, rotulo in Indicador.AREA_CHOICES
        ]
        return context


class IndicadorCreate(CreateView):
    model = Indicador
    form_class = IndicadorForm
    template_name = 'indicadores/form.html'
    success_url = reverse_lazy('indicadores:listar')

    def get_initial(self):
        initial = super().get_initial()
        area = (self.request.GET.get('area') or '').strip().upper()
        if area in dict(Indicador.AREA_CHOICES):
            initial['area'] = area
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Adicionar Indicador'
        context['titulo'] = 'Indicador'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if not empresa_id:
            messages.error(self.request, 'Selecione uma empresa.')
            return redirect('empresa:trocar')
        form.instance.empresa_id = empresa_id
        messages.success(self.request, 'Indicador criado com sucesso.')
        return super().form_valid(form)


class IndicadorUpdate(UpdateView):
    model = Indicador
    form_class = IndicadorForm
    template_name = 'indicadores/form.html'
    success_url = reverse_lazy('indicadores:listar')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['descricao'] = 'Alterar Indicador'
        context['titulo'] = 'Indicador'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Indicador atualizado com sucesso.')
        return super().form_valid(form)


class IndicadorDelete(DeleteView):
    model = Indicador
    success_url = reverse_lazy('indicadores:listar')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, 'Indicador excluído.')
        return super().form_valid(form)
