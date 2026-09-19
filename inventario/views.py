from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.utils import DatabaseError
from django.forms import modelformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic.list import ListView

from inventario.forms import (
    InventarioAdicionarProdutosForm,
    InventarioForm,
    InventarioItemContagemForm,
)
from inventario.backup_estoque import (
    aplicar_contagem_ao_estoque,
    backup_para_excel,
    criar_backup_estoque,
)
from inventario.models import (
    EstoqueBackup,
    Inventario,
    InventarioItem,
    InventarioResponsavelContagem,
)
from inventario.services import (
    popular_itens_do_estoque,
    salvar_responsaveis,
    usuario_pode_contar,
)


class _EmpresaInventarioMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs


class InventarioListView(LoginRequiredMixin, _EmpresaInventarioMixin, ListView):
    model = Inventario
    paginate_by = 20
    template_name = 'inventario/inventario_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Inventário'
        return ctx


class InventarioCreateView(LoginRequiredMixin, CreateView):
    model = Inventario
    form_class = InventarioForm
    template_name = 'inventario/inventario_form.html'
    def get_success_url(self):
        return reverse('inventario:inventario_detail', kwargs={'pk': self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa_id'] = self.request.session.get('empresa_id')
        return kwargs

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if not empresa_id:
            messages.error(self.request, 'Selecione uma empresa antes de abrir um inventário.')
            return redirect('empresa:lista')
        form.instance.empresa_id = empresa_id
        form.instance.criado_por = self.request.user
        response = super().form_valid(form)
        salvar_responsaveis(self.object, form.responsaveis_por_rodada())
        try:
            criados = popular_itens_do_estoque(
                self.object,
                produto_ids=form.produtos_selecionados_ids(),
            )
            bkp = criar_backup_estoque(self.object, self.request.user)
        except DatabaseError:
            messages.error(
                self.request,
                'Erro ao carregar produtos do estoque. No servidor, execute '
                'python manage.py migrate (apps estoque e inventário).',
            )
            return redirect('inventario:inventario_detail', pk=self.object.pk)
        msg = (
            f'Inventário criado com {criados} produto(s). Backup do estoque '
            f'({bkp.linhas.count()} itens) gravado.'
        )
        if criados == 0:
            messages.warning(
                self.request,
                'Nenhum produto na contagem. Cadastre produtos em Estoque ou use '
                '«Escolher produtos» na tela do inventário.',
            )
        else:
            messages.success(self.request, msg)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Novo inventário'
        return ctx


class InventarioUpdateView(LoginRequiredMixin, _EmpresaInventarioMixin, UpdateView):
    model = Inventario
    form_class = InventarioForm
    template_name = 'inventario/inventario_form.html'

    def get_success_url(self):
        return reverse('inventario:inventario_detail', kwargs={'pk': self.object.pk})

    def get_initial(self):
        initial = super().get_initial()
        inv = self.object
        for rodada in (1, 2, 3):
            ids = InventarioResponsavelContagem.objects.filter(
                inventario=inv,
                rodada=rodada,
            ).values_list('usuario_id', flat=True)
            initial[f'usuarios_contagem_{rodada}'] = list(ids)
        return initial

    def form_valid(self, form):
        if not self.object.aberto:
            messages.error(self.request, 'Inventário fechado — não é possível alterar responsáveis.')
            return redirect('inventario:inventario_detail', pk=self.object.pk)
        response = super().form_valid(form)
        salvar_responsaveis(self.object, form.responsaveis_por_rodada())
        messages.success(self.request, 'Responsáveis atualizados.')
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Configurar inventário'
        return ctx


class InventarioDetailView(LoginRequiredMixin, _EmpresaInventarioMixin, DetailView):
    model = Inventario
    template_name = 'inventario/inventario_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        inv = self.object
        ctx['descricao'] = inv.descricao
        ctx['itens'] = inv.itens.select_related(
            'contagem_1_por',
            'contagem_2_por',
            'contagem_3_por',
        )
        ctx['responsaveis'] = {
            str(rodada): list(
                InventarioResponsavelContagem.objects.filter(inventario=inv, rodada=rodada)
                .select_related('usuario')
                .order_by('usuario__username'),
            )
            for rodada in (1, 2, 3)
        }
        ctx['pode_contar'] = {
            str(rodada): usuario_pode_contar(inv, self.request.user, rodada)
            for rodada in (1, 2, 3)
        }
        ctx['rodada_estoque'] = inv.rodada_atualiza_estoque
        ctx['ultimo_backup'] = (
            inv.backups_estoque.prefetch_related('linhas').order_by('-criado_em').first()
        )
        ctx['total_itens'] = inv.itens.count()
        return ctx


def _inventario_da_sessao(request, pk):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return None
    return get_object_or_404(Inventario, pk=pk, empresa_id=empresa_id)


@login_required
def inventario_contagem(request, pk, rodada):
    if rodada not in (1, 2, 3):
        messages.error(request, 'Rodada de contagem inválida.')
        return redirect('inventario:inventario_list')

    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')

    if not inventario.aberto:
        messages.error(request, 'Este inventário está fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    if not usuario_pode_contar(inventario, request.user, rodada):
        messages.error(request, f'Você não está autorizado a lançar a {rodada}ª contagem.')
        return redirect('inventario:inventario_detail', pk=pk)

    FormSet = modelformset_factory(
        InventarioItem,
        form=InventarioItemContagemForm,
        extra=0,
        can_delete=False,
    )

    queryset = inventario.itens.all().order_by('codigo_produto', 'descricao_produto')
    prefix = f'r{rodada}'

    if request.method == 'POST':
        formset = FormSet(
            request.POST,
            queryset=queryset,
            prefix=prefix,
            form_kwargs={'rodada': rodada},
        )
        if formset.is_valid():
            agora = timezone.now()
            usuario = request.user
            campo_qtd = f'contagem_{rodada}'
            campo_em = f'contagem_{rodada}_em'
            campo_por = f'contagem_{rodada}_por'
            alterados = 0
            for form in formset:
                item = form.instance
                valor = form.cleaned_data.get('contagem_valor')
                setattr(item, campo_qtd, valor)
                if valor is not None:
                    setattr(item, campo_em, agora)
                    setattr(item, campo_por, usuario)
                else:
                    setattr(item, campo_em, None)
                    setattr(item, campo_por, None)
                item.save(
                    update_fields=[campo_qtd, campo_em, campo_por],
                )
                alterados += 1
            messages.success(request, f'{rodada}ª contagem gravada ({alterados} linha(s)).')
            return redirect('inventario:inventario_contagem', pk=pk, rodada=rodada)
    else:
        formset = FormSet(
            queryset=queryset,
            prefix=prefix,
            form_kwargs={'rodada': rodada},
        )

    total_itens = queryset.count()
    return render(
        request,
        'inventario/inventario_contagem.html',
        {
            'descricao': f'{inventario.descricao} — {rodada}ª contagem',
            'inventario': inventario,
            'rodada': rodada,
            'formset': formset,
            'total_itens': total_itens,
        },
    )


@login_required
@require_POST
def inventario_sincronizar_estoque(request, pk):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')

    if not inventario.aberto:
        messages.error(request, 'Inventário fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    try:
        criados = popular_itens_do_estoque(inventario)
    except DatabaseError:
        messages.error(
            request,
            'Não foi possível sincronizar. Execute migrate no servidor (estoque e inventário).',
        )
        return redirect('inventario:inventario_detail', pk=pk)
    if criados:
        messages.info(request, f'{criados} produto(s) novo(s) incluído(s) a partir do estoque.')
    else:
        messages.warning(
            request,
            'Nenhum produto novo. Cadastre em Estoque ou use «Escolher produtos».',
        )
    return redirect('inventario:inventario_detail', pk=pk)


@login_required
def inventario_produtos(request, pk):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    if not inventario.aberto:
        messages.error(request, 'Inventário fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    if request.method == 'POST':
        form = InventarioAdicionarProdutosForm(request.POST, inventario=inventario)
        if form.is_valid():
            ids = list(form.cleaned_data['produtos'].values_list('pk', flat=True))
            try:
                criados = popular_itens_do_estoque(inventario, produto_ids=ids)
            except DatabaseError:
                messages.error(request, 'Erro ao incluir produtos. Verifique migrate no servidor.')
                return redirect('inventario:inventario_produtos', pk=pk)
            messages.success(request, f'{criados} produto(s) incluído(s) na contagem.')
            return redirect('inventario:inventario_detail', pk=pk)
    else:
        form = InventarioAdicionarProdutosForm(inventario=inventario)

    itens = inventario.itens.order_by('codigo_produto', 'descricao_produto')
    return render(
        request,
        'inventario/inventario_produtos.html',
        {
            'descricao': f'{inventario.descricao} — produtos',
            'inventario': inventario,
            'form': form,
            'itens': itens,
        },
    )


@login_required
@require_POST
def inventario_remover_item(request, pk, item_id):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    if not inventario.aberto:
        messages.error(request, 'Inventário fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    item = get_object_or_404(InventarioItem, pk=item_id, inventario=inventario)
    if any(item.valor_contagem(r) is not None for r in (1, 2, 3)):
        messages.error(request, 'Não é possível remover: já existe contagem neste produto.')
        return redirect('inventario:inventario_produtos', pk=pk)
    item.delete()
    messages.success(request, 'Produto removido deste inventário.')
    return redirect('inventario:inventario_produtos', pk=pk)


@login_required
@require_POST
def inventario_backup_estoque(request, pk):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    if not inventario.aberto:
        messages.error(request, 'Inventário fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    bkp = criar_backup_estoque(inventario, request.user, descricao='Backup manual')
    messages.success(request, f'Backup do estoque salvo ({bkp.linhas.count()} produtos).')
    return redirect('inventario:inventario_detail', pk=pk)


@login_required
def inventario_backup_excel(request, pk, backup_id):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')

    backup = get_object_or_404(EstoqueBackup, pk=backup_id, inventario=inventario)
    data = backup_para_excel(backup)
    nome = f'backup_estoque_inv{inventario.pk}_{backup.criado_em:%Y%m%d_%H%M}.xlsx'
    response = HttpResponse(
        data,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{nome}"'
    return response


@login_required
@require_POST
def inventario_definir_rodada_estoque(request, pk):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    if not inventario.aberto:
        messages.error(request, 'Inventário fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    try:
        rodada = int(request.POST.get('rodada_atualiza_estoque', '0'))
    except (TypeError, ValueError):
        rodada = 0
    if rodada not in (0, 1, 2, 3):
        messages.error(request, 'Rodada inválida.')
        return redirect('inventario:inventario_detail', pk=pk)

    inventario.rodada_atualiza_estoque = rodada
    inventario.save(update_fields=['rodada_atualiza_estoque'])
    if rodada:
        messages.success(request, f'{rodada}ª contagem selecionada para atualizar o estoque.')
    else:
        messages.info(request, 'Nenhuma contagem selecionada para atualizar o estoque.')
    return redirect('inventario:inventario_detail', pk=pk)


@login_required
@require_POST
def inventario_aplicar_estoque(request, pk):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    if not inventario.aberto:
        messages.error(request, 'Inventário fechado.')
        return redirect('inventario:inventario_detail', pk=pk)

    try:
        stats = aplicar_contagem_ao_estoque(inventario, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('inventario:inventario_detail', pk=pk)

    messages.success(
        request,
        f'Estoque atualizado: {stats["atualizados"]} produto(s); '
        f'{stats["ignorados"]} sem contagem na rodada escolhida.',
    )
    return redirect('inventario:inventario_detail', pk=pk)


@login_required
@require_POST
def inventario_fechar(request, pk):
    inventario = _inventario_da_sessao(request, pk)
    if inventario is None:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')

    inventario.aberto = False
    inventario.save(update_fields=['aberto'])
    messages.success(request, 'Inventário fechado.')
    return redirect('inventario:inventario_detail', pk=pk)
