from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from estoque.forms_operacional import GerarEstoqueNotaForm, RelatorioEstoqueForm, RequisicaoEstoqueForm
from estoque.models import (
    EntradaEstoqueNota,
    MovimentoEstoque,
    ProdutoEstoque,
    RequisicaoEstoque,
    RequisicaoEstoqueItem,
    SaldoEstoqueSetor,
)
from estoque.permissoes import (
    usuario_e_admin_estoque,
    usuario_pode_baixa_setor,
    usuario_pode_requisicao_farmacia,
)
from estoque.alertas import contar_abaixo_estoque_minimo, queryset_abaixo_estoque_minimo
from estoque.services.movimentacao import EstoqueErro, concluir_requisicao, gerar_entrada_desde_item_nota
from estoque.setores import SetorEstoque
from notafiscalentrada.models import NotaFiscalEntradaItem


class _EmpresaMixin:
    def get_empresa_id(self):
        return self.request.session.get('empresa_id')


class EstoqueFarmaciaListView(LoginRequiredMixin, _EmpresaMixin, ListView):
    """Visão operacional — farmácia (Fiscal)."""

    model = ProdutoEstoque
    paginate_by = 30
    template_name = 'estoque/farmacia_list.html'

    def get_queryset(self):
        empresa_id = self.get_empresa_id()
        somente_alertas = (self.request.GET.get('somente_alertas') or '').strip() in ('1', 'true', 'sim')
        if somente_alertas and empresa_id:
            qs = queryset_abaixo_estoque_minimo(empresa_id)
        else:
            qs = ProdutoEstoque.objects.filter(empresa_id=empresa_id) if empresa_id else ProdutoEstoque.objects.none()
        qs = qs.select_related('fornecedor')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(codigo_produto__icontains=q)
                | Q(descricao__icontains=q)
                | Q(marca__icontains=q)
            )
        return qs.order_by('descricao')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        empresa_id = self.get_empresa_id()
        ctx['descricao'] = 'Estoque — Farmácia'
        ctx['busca'] = (self.request.GET.get('q') or '').strip()
        ctx['somente_alertas'] = (self.request.GET.get('somente_alertas') or '').strip() in (
            '1',
            'true',
            'sim',
        )
        ctx['total_alertas_minimo'] = contar_abaixo_estoque_minimo(empresa_id)
        amostra = list(queryset_abaixo_estoque_minimo(empresa_id)[:8])
        ctx['alertas_amostra'] = amostra
        ctx['alertas_restantes'] = max(0, ctx['total_alertas_minimo'] - len(amostra))
        return ctx


class ProdutoEstoqueOperacionalDetailView(LoginRequiredMixin, _EmpresaMixin, DetailView):
    model = ProdutoEstoque
    template_name = 'estoque/produto_operacional_detail.html'
    context_object_name = 'produto'

    def get_queryset(self):
        empresa_id = self.get_empresa_id()
        return ProdutoEstoque.objects.filter(empresa_id=empresa_id)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        p = self.object
        ctx['entradas_nota'] = (
            EntradaEstoqueNota.objects.filter(produto=p)
            .select_related('nota_item__nota_fiscal', 'criado_por')
            .order_by('-criado_em')
        )
        ctx['movimentos'] = MovimentoEstoque.objects.filter(produto=p).select_related(
            'requisicao', 'usuario'
        )[:100]
        ctx['saldos_setor'] = SaldoEstoqueSetor.objects.filter(produto=p).exclude(quantidade=0)
        ctx['descricao'] = f'Estoque — {p.codigo_produto}'
        return ctx


@login_required
@require_POST
def gerar_estoque_item_nota(request, item_id: int):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('notafiscalentrada:produtos_comercio')

    item = get_object_or_404(
        NotaFiscalEntradaItem,
        pk=item_id,
        nota_fiscal__empresa_id=empresa_id,
        nota_fiscal__tipo_nota='comercio',
    )
    form = GerarEstoqueNotaForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Dados inválidos para gerar estoque.')
        return redirect(request.META.get('HTTP_REFERER') or reverse('notafiscalentrada:produtos_comercio'))

    try:
        gerar_entrada_desde_item_nota(
            item,
            usuario=request.user,
            marca=form.cleaned_data.get('marca') or '',
            unidade_master=form.cleaned_data.get('unidade_master') or '',
            data_validade=form.cleaned_data.get('data_validade'),
        )
        messages.success(request, f'Estoque atualizado para {item.codigo_produto}.')
    except EstoqueErro as exc:
        messages.warning(request, str(exc))

    return redirect(request.META.get('HTTP_REFERER') or reverse('notafiscalentrada:produtos_comercio'))


class RequisicaoListView(LoginRequiredMixin, _EmpresaMixin, ListView):
    model = RequisicaoEstoque
    paginate_by = 25
    template_name = 'estoque/requisicao_list.html'

    def get_queryset(self):
        empresa_id = self.get_empresa_id()
        if not empresa_id:
            return RequisicaoEstoque.objects.none()
        return RequisicaoEstoque.objects.filter(empresa_id=empresa_id).select_related('criado_por')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Requisições de estoque'
        ctx['pode_farmacia'] = usuario_pode_requisicao_farmacia(self.request.user)
        return ctx


def _validar_permissao_requisicao(request, empresa_id: int, tipo: str, setor_origem: str) -> bool:
    if tipo in (RequisicaoEstoque.Tipo.TRANSFERENCIA, RequisicaoEstoque.Tipo.BAIXA_FARMACIA):
        if not usuario_pode_requisicao_farmacia(request.user):
            messages.error(request, 'Sem permissão para requisição da farmácia.')
            return False
    if tipo == RequisicaoEstoque.Tipo.BAIXA_SETOR:
        if not usuario_pode_baixa_setor(request.user, empresa_id, setor_origem):
            messages.error(request, 'Você não é responsável por este setor.')
            return False
    return True


def _aplicar_setores_requisicao(req: RequisicaoEstoque) -> None:
    if req.tipo in (
        RequisicaoEstoque.Tipo.TRANSFERENCIA,
        RequisicaoEstoque.Tipo.BAIXA_FARMACIA,
    ):
        req.setor_origem = SetorEstoque.FARMACIA
        req.setor_consumo = req.setor_destino
    elif req.tipo == RequisicaoEstoque.Tipo.BAIXA_SETOR:
        req.setor_destino = ''
        req.setor_consumo = req.setor_origem


def _contexto_requisicao_tela(
    request,
    *,
    requisicao: RequisicaoEstoque | None,
    form: RequisicaoEstoqueForm,
    empresa_id: int,
):
    itens = []
    produtos = ProdutoEstoque.objects.none()
    if empresa_id:
        produtos = ProdutoEstoque.objects.filter(empresa_id=empresa_id).order_by('descricao')[:800]
    if requisicao:
        itens = requisicao.itens.select_related('produto')
    descricao = 'Nova requisição' if not requisicao else f'Requisição #{requisicao.pk}'
    return {
        'requisicao': requisicao,
        'form': form,
        'itens': itens,
        'produtos': produtos,
        'descricao': descricao,
        'pode_editar': not requisicao or requisicao.status == RequisicaoEstoque.Status.RASCUNHO,
        'pode_reabrir': bool(
            requisicao
            and requisicao.status == RequisicaoEstoque.Status.CANCELADA
            and not requisicao.movimentos.exists()
        ),
    }


@login_required
def requisicao_nova(request):
    return requisicao_edit(request, pk=None)


@login_required
def requisicao_detail(request, pk: int):
    return requisicao_edit(request, pk=pk)


@login_required
def requisicao_edit(request, pk: int | None):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:requisicao_list')

    requisicao = None
    if pk is not None:
        requisicao = get_object_or_404(RequisicaoEstoque, pk=pk, empresa_id=empresa_id)

    if request.method == 'POST':
        acao = (request.POST.get('acao') or 'cabecalho').strip()

        if acao == 'cabecalho':
            if requisicao and requisicao.status != RequisicaoEstoque.Status.RASCUNHO:
                messages.error(request, 'Requisição não está em rascunho.')
                return redirect('estoque:requisicao_detail', pk=requisicao.pk)

            form = RequisicaoEstoqueForm(request.POST, instance=requisicao)
            if form.is_valid():
                tipo = form.cleaned_data['tipo']
                origem = form.cleaned_data.get('setor_origem') or ''
                if not _validar_permissao_requisicao(request, empresa_id, tipo, origem):
                    return render(
                        request,
                        'estoque/requisicao_edit.html',
                        _contexto_requisicao_tela(
                            request,
                            requisicao=requisicao,
                            form=form,
                            empresa_id=empresa_id,
                        ),
                    )

                req = form.save(commit=False)
                req.empresa_id = empresa_id
                if not requisicao:
                    req.criado_por = request.user
                _aplicar_setores_requisicao(req)
                req.save()
                if not pk:
                    messages.success(
                        request,
                        'Cabeçalho salvo. Escolha o produto e a quantidade na seção «Produtos» abaixo.',
                    )
                    return redirect(
                        reverse('estoque:requisicao_detail', kwargs={'pk': req.pk}) + '#secao-produtos',
                    )
                messages.success(request, 'Cabeçalho atualizado.')
                return redirect('estoque:requisicao_detail', pk=requisicao.pk)

            return render(
                request,
                'estoque/requisicao_edit.html',
                _contexto_requisicao_tela(
                    request,
                    requisicao=requisicao,
                    form=form,
                    empresa_id=empresa_id,
                ),
            )

        if not requisicao:
            return redirect('estoque:requisicao_nova')

        if acao == 'reabrir':
            if requisicao.status != RequisicaoEstoque.Status.CANCELADA:
                messages.error(request, 'Só é possível reabrir requisição cancelada.')
            elif requisicao.movimentos.exists():
                messages.error(request, 'Esta requisição já movimentou estoque; crie uma nova.')
            else:
                requisicao.status = RequisicaoEstoque.Status.RASCUNHO
                requisicao.save(update_fields=['status'])
                messages.success(request, 'Requisição reaberta. Inclua os produtos e conclua quando pronto.')
            return redirect('estoque:requisicao_detail', pk=requisicao.pk)

        if requisicao.status != RequisicaoEstoque.Status.RASCUNHO:
            messages.error(request, 'Requisição não está em rascunho.')
            return redirect('estoque:requisicao_detail', pk=requisicao.pk)

        if acao == 'add_item':
            produto_id = request.POST.get('produto_id')
            qtd = request.POST.get('quantidade') or '0'
            try:
                q = Decimal(str(qtd).replace(',', '.'))
            except Exception:
                q = Decimal('0')
            produto = get_object_or_404(ProdutoEstoque, pk=produto_id, empresa_id=empresa_id)
            if q > 0:
                RequisicaoEstoqueItem.objects.create(
                    requisicao=requisicao,
                    produto=produto,
                    quantidade=q,
                )
                messages.success(request, 'Produto incluído na grade.')
        elif acao == 'remover_item':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(
                RequisicaoEstoqueItem,
                pk=item_id,
                requisicao=requisicao,
            )
            item.delete()
            messages.info(request, 'Linha removida.')
        elif acao == 'concluir':
            try:
                produto_ids = list(requisicao.itens.values_list('produto_id', flat=True))
                concluir_requisicao(requisicao, usuario=request.user)
                messages.success(request, 'Requisição concluída.')
                abaixo = queryset_abaixo_estoque_minimo(empresa_id).filter(pk__in=produto_ids).count()
                if abaixo:
                    messages.warning(
                        request,
                        f'Alerta: {abaixo} produto(s) desta requisição ficaram abaixo do estoque mínimo. '
                        f'Veja em Estoque (Farmácia) → Alertas.',
                    )
            except EstoqueErro as exc:
                messages.error(request, str(exc))
            except ValueError as exc:
                messages.error(request, f'Não foi possível concluir: {exc}')
        elif acao == 'cancelar':
            requisicao.status = RequisicaoEstoque.Status.CANCELADA
            requisicao.save(update_fields=['status'])
            messages.info(request, 'Requisição cancelada. Você pode reabrir como rascunho se ainda não concluiu.')

        return redirect('estoque:requisicao_detail', pk=requisicao.pk)

    if requisicao:
        form = RequisicaoEstoqueForm(instance=requisicao)
    else:
        form = RequisicaoEstoqueForm(initial={'setor_origem': SetorEstoque.FARMACIA})

    return render(
        request,
        'estoque/requisicao_edit.html',
        _contexto_requisicao_tela(request, requisicao=requisicao, form=form, empresa_id=empresa_id),
    )


@login_required
def relatorio_movimentos(request):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('dashboard:relatorio_mensal')

    hoje = timezone.localdate()
    form = RelatorioEstoqueForm(request.GET or None)
    movimentos = MovimentoEstoque.objects.filter(empresa_id=empresa_id).select_related('produto', 'usuario')

    if form.is_valid():
        prod = (form.cleaned_data.get('produto') or '').strip()
        setor = form.cleaned_data.get('setor') or ''
        di = form.cleaned_data.get('data_inicio')
        df = form.cleaned_data.get('data_fim')
        if prod:
            movimentos = movimentos.filter(
                Q(produto__descricao__icontains=prod)
                | Q(produto__codigo_produto__icontains=prod)
            )
        if setor:
            movimentos = movimentos.filter(
                Q(setor_origem=setor) | Q(setor_destino=setor) | Q(requisicao__setor_consumo=setor)
            )
        if di:
            movimentos = movimentos.filter(criado_em__date__gte=di)
        if df:
            movimentos = movimentos.filter(criado_em__date__lte=df)
    else:
        movimentos = movimentos.filter(
            criado_em__date__gte=hoje.replace(day=1),
            criado_em__date__lte=hoje,
        )
        form = RelatorioEstoqueForm(
            initial={'data_inicio': hoje.replace(day=1), 'data_fim': hoje},
        )

    resumo = movimentos.filter(tipo=MovimentoEstoque.Tipo.BAIXA).values(
        'produto__codigo_produto',
        'produto__descricao',
        'setor_destino',
    ).annotate(total=Sum('quantidade')).order_by('-total')[:50]

    return render(
        request,
        'estoque/relatorio_movimentos.html',
        {
            'form': form,
            'movimentos': movimentos.order_by('-criado_em')[:500],
            'resumo_baixas': resumo,
            'descricao': 'Relatório de estoque',
        },
    )
