from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, OperationalError
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from estoque.forms_operacional import GerarEstoqueNotaForm, RelatorioEstoqueForm, RequisicaoEstoqueForm
from estoque.models import (
    EntradaEstoqueNota,
    MovimentoEstoque,
    NaturezaEstoque,
    ProdutoEstoque,
    RequisicaoEstoque,
    RequisicaoEstoqueItem,
    SaldoEstoqueSetor,
)
from estoque.permissoes import (
    usuario_e_admin_estoque,
    usuario_pode_baixa_setor,
    usuario_pode_requisicao_farmacia,
    validar_senha_aprovacao_estorno_nf,
)
from estoque.alertas import contar_abaixo_estoque_minimo, queryset_abaixo_estoque_minimo
from estoque.services.movimentacao import (
    EstoqueErro,
    concluir_requisicao,
    estornar_entrada_desde_item_nota,
    gerar_entrada_desde_item_nota,
    pode_estornar_entrada_nota,
)
from estoque.setores import (
    SETOR_LISTA_CEGA_FARMACIA,
    SETOR_LOCALIZACAO_IMOBILIZADO,
    SetorEstoque,
    rotulo_setor,
)
from empresa.models import Empresa
from notafiscalentrada.models import NotaFiscalEntradaItem


class _EmpresaMixin:
    def get_empresa_id(self):
        return self.request.session.get('empresa_id')


def _redirect_voltar_produtos_comercio(request, *, destino_estoque: str = ''):
    referer = (request.META.get('HTTP_REFERER') or '').strip()
    if referer and referer.startswith(('http://', 'https://')):
        return redirect(referer)
    url = reverse('notafiscalentrada:produtos_comercio')
    if destino_estoque == 'imobilizado':
        return redirect(url + '?destino_estoque=imobilizado')
    return redirect(url)


class _ProdutoEstoqueFiscalListMixin(_EmpresaMixin):
    model = ProdutoEstoque
    paginate_by = 30
    natureza_filtro = NaturezaEstoque.CONSUMIVEL

    def _queryset_base(self):
        empresa_id = self.get_empresa_id()
        if not empresa_id:
            return ProdutoEstoque.objects.none()
        return ProdutoEstoque.objects.filter(
            empresa_id=empresa_id,
            natureza=self.natureza_filtro,
        ).select_related('fornecedor')

    def _aplicar_busca(self, qs):
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(codigo_produto__icontains=q)
                | Q(descricao__icontains=q)
                | Q(marca__icontains=q),
            )
        return qs.order_by('descricao')


class EstoqueFarmaciaListView(LoginRequiredMixin, _ProdutoEstoqueFiscalListMixin, ListView):
    """Visão operacional — farmácia (Fiscal)."""

    template_name = 'estoque/farmacia_list.html'

    def get_queryset(self):
        somente_alertas = (self.request.GET.get('somente_alertas') or '').strip() in ('1', 'true', 'sim')
        if somente_alertas:
            qs = queryset_abaixo_estoque_minimo(self.get_empresa_id())
        else:
            qs = self._queryset_base()
        return self._aplicar_busca(qs)

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


class EstoqueImobilizadoListView(LoginRequiredMixin, _ProdutoEstoqueFiscalListMixin, ListView):
    """Patrimônio / bens — entradas via NF comércio (Fiscal)."""

    natureza_filtro = NaturezaEstoque.IMOBILIZADO
    template_name = 'estoque/imobilizado_list.html'

    def get_queryset(self):
        qs = self._queryset_base()
        setor = (self.request.GET.get('setor') or '').strip()
        if setor == '__sem__':
            qs = qs.filter(Q(setor_localizacao='') | Q(setor_localizacao__isnull=True))
        elif setor:
            qs = qs.filter(setor_localizacao=setor)
        return self._aplicar_busca(qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['descricao'] = 'Estoque — Imobilizado'
        ctx['busca'] = (self.request.GET.get('q') or '').strip()
        ctx['filtro_setor'] = (self.request.GET.get('setor') or '').strip()
        ctx['setores_imobilizado'] = SETOR_LOCALIZACAO_IMOBILIZADO
        empresa_id = self.get_empresa_id()
        if empresa_id:
            ctx['total_sem_setor'] = ProdutoEstoque.objects.filter(
                empresa_id=empresa_id,
                natureza=NaturezaEstoque.IMOBILIZADO,
            ).filter(Q(setor_localizacao='') | Q(setor_localizacao__isnull=True)).count()
        else:
            ctx['total_sem_setor'] = 0
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
        entradas = list(
            EntradaEstoqueNota.objects.filter(produto=p)
            .select_related('nota_item__nota_fiscal', 'criado_por', 'movimento')
            .order_by('-criado_em'),
        )
        for e in entradas:
            e.pode_estornar = pode_estornar_entrada_nota(e)
            dest = e.movimento.setor_destino if e.movimento_id else ''
            if p.natureza == NaturezaEstoque.IMOBILIZADO:
                e.setor_rotulo = (
                    p.get_setor_localizacao_display()
                    if p.setor_localizacao
                    else rotulo_setor(dest)
                )
            else:
                e.setor_rotulo = rotulo_setor(dest)
        ctx['entradas_nota'] = entradas
        ctx['movimentos'] = MovimentoEstoque.objects.filter(produto=p).select_related(
            'requisicao', 'usuario'
        )[:100]
        ctx['saldos_setor'] = SaldoEstoqueSetor.objects.filter(produto=p).exclude(quantidade=0)
        ctx['descricao'] = f'Estoque — {p.codigo_produto}'
        ctx['voltar_estoque_url'] = (
            reverse('estoque:imobilizado_list')
            if p.natureza == NaturezaEstoque.IMOBILIZADO
            else reverse('estoque:farmacia_list')
        )
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
    destino_post = (request.POST.get('natureza') or '').strip()
    form = GerarEstoqueNotaForm(request.POST)
    if not form.is_valid():
        erros = '; '.join(
            f'{campo}: {", ".join(lista)}' for campo, lista in form.errors.items()
        )
        messages.error(request, f'Não foi possível gerar estoque. {erros}')
        return _redirect_voltar_produtos_comercio(
            request,
            destino_estoque='imobilizado' if destino_post == NaturezaEstoque.IMOBILIZADO else '',
        )

    try:
        natureza = form.cleaned_data.get('natureza') or NaturezaEstoque.CONSUMIVEL
        gerar_entrada_desde_item_nota(
            item,
            usuario=request.user,
            marca=form.cleaned_data.get('marca') or '',
            unidade_master=form.cleaned_data.get('unidade_master') or '',
            quantidade_por_master=form.cleaned_data.get('quantidade_por_master'),
            unidade_consumo=form.cleaned_data.get('unidade_consumo') or '',
            data_validade=form.cleaned_data.get('data_validade'),
            natureza=natureza,
            setor_localizacao=form.cleaned_data.get('setor_localizacao') or '',
        )
        destino = (
            'imobilizado'
            if natureza == NaturezaEstoque.IMOBILIZADO
            else 'farmácia'
        )
        messages.success(request, f'Entrada no estoque ({destino}) para {item.codigo_produto}.')
    except EstoqueErro as exc:
        messages.warning(request, str(exc))
    except IntegrityError:
        messages.warning(request, 'Este item da NF já possui entrada de estoque registrada.')
    except OperationalError:
        messages.error(
            request,
            'Banco desatualizado (migrations pendentes no servidor). '
            'Execute migrate estoque até 0009 no Render.',
        )
    except Exception as exc:
        messages.error(request, f'Erro ao gerar estoque: {exc}')

    return _redirect_voltar_produtos_comercio(
        request,
        destino_estoque='imobilizado' if destino_post == NaturezaEstoque.IMOBILIZADO else '',
    )


_SETOR_IMOBILIZADO_VALIDOS = frozenset(v for v, _ in SETOR_LOCALIZACAO_IMOBILIZADO)


@login_required
@require_POST
def atualizar_setor_imobilizado(request, pk: int):
    """Define setor clínico na grade de imobilizado (sem abrir cadastro completo)."""
    empresa_id = request.session.get('empresa_id')
    voltar = (request.POST.get('next') or '').strip()
    if not voltar.startswith('/'):
        voltar = reverse('estoque:imobilizado_list')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:imobilizado_list')

    produto = get_object_or_404(
        ProdutoEstoque,
        pk=pk,
        empresa_id=empresa_id,
        natureza=NaturezaEstoque.IMOBILIZADO,
    )
    setor = (request.POST.get('setor_localizacao') or '').strip()
    if setor and setor not in _SETOR_IMOBILIZADO_VALIDOS:
        messages.error(request, 'Setor inválido.')
        return redirect(voltar)

    produto.setor_localizacao = setor[:32]
    produto.save(update_fields=['setor_localizacao'])
    if setor:
        messages.success(
            request,
            f'Setor de {produto.codigo_produto} atualizado para {produto.get_setor_localizacao_display()}.',
        )
    else:
        messages.success(request, f'Setor de {produto.codigo_produto} removido.')
    return redirect(voltar)


@login_required
@require_POST
def estornar_estoque_nf_item(request, item_id: int):
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
    senha_ok, msg_senha = validar_senha_aprovacao_estorno_nf(request.POST.get('senha_aprovacao'))
    if not senha_ok:
        messages.error(request, msg_senha)
        return redirect(request.META.get('HTTP_REFERER') or reverse('notafiscalentrada:produtos_comercio'))

    try:
        estornar_entrada_desde_item_nota(item, usuario=request.user)
        messages.success(
            request,
            f'Entrada estornada para {item.codigo_produto}. '
            'Na NF Comércio, use «Lançar imobilizado» (tela Estoque imobilizado).',
        )
    except EstoqueErro as exc:
        messages.error(request, str(exc))

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
        produtos = (
            ProdutoEstoque.objects.filter(
                empresa_id=empresa_id,
                natureza=NaturezaEstoque.CONSUMIVEL,
            )
            .order_by('descricao')[:800]
        )
    if requisicao:
        itens = requisicao.itens.select_related('produto')
    if not requisicao:
        descricao = 'Nova requisição'
    elif requisicao.status == RequisicaoEstoque.Status.RASCUNHO:
        descricao = f'Requisição #{requisicao.pk} · Rascunho'
    else:
        descricao = f'Requisição #{requisicao.pk}'
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

        if acao in ('cabecalho', 'cabecalho_rascunho'):
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
                req.status = RequisicaoEstoque.Status.RASCUNHO
                if not requisicao:
                    req.criado_por = request.user
                _aplicar_setores_requisicao(req)
                req.save()
                if acao == 'cabecalho_rascunho':
                    messages.success(
                        request,
                        f'Requisição #{req.pk} salva como rascunho. '
                        'Inclua os produtos e conclua após a conferência.',
                    )
                    return redirect('estoque:requisicao_list')
                if not pk:
                    messages.success(
                        request,
                        'Cabeçalho salvo em rascunho. Escolha o produto e a quantidade na seção «Produtos» abaixo.',
                    )
                    return redirect(
                        reverse('estoque:requisicao_detail', kwargs={'pk': req.pk}) + '#secao-produtos',
                    )
                messages.success(request, 'Cabeçalho atualizado (rascunho).')
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
        elif acao == 'salvar_rascunho':
            messages.success(
                request,
                f'Requisição #{requisicao.pk} permanece em rascunho. '
                'Abra na lista e use «Concluir requisição» após a conferência.',
            )
            return redirect('estoque:requisicao_list')
        elif acao == 'concluir':
            concluido_ok = False
            try:
                produto_ids = list(requisicao.itens.values_list('produto_id', flat=True))
                concluir_requisicao(requisicao, usuario=request.user)
                concluido_ok = True
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
            if concluido_ok:
                return redirect(
                    reverse('estoque:requisicao_imprimir', kwargs={'pk': requisicao.pk}) + '?auto=1',
                )
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


def _setor_rotulo_requisicao(requisicao: RequisicaoEstoque) -> str:
    if requisicao.setor_destino:
        return requisicao.get_setor_destino_display()
    if requisicao.tipo == RequisicaoEstoque.Tipo.BAIXA_SETOR:
        return requisicao.get_setor_origem_display()
    return ''


@login_required
def requisicao_imprimir(request, pk: int):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:requisicao_list')

    requisicao = get_object_or_404(RequisicaoEstoque, pk=pk, empresa_id=empresa_id)
    itens = requisicao.itens.select_related('produto').order_by('produto__descricao')

    from empresa.models import Empresa

    empresa = Empresa.objects.filter(pk=empresa_id).first()
    auto_print = (request.GET.get('auto') or '').strip() in ('1', 'true', 'sim')

    return render(
        request,
        'estoque/requisicao_imprimir.html',
        {
            'requisicao': requisicao,
            'itens': itens,
            'empresa': empresa,
            'setor_rotulo': _setor_rotulo_requisicao(requisicao),
            'agora': timezone.now(),
            'auto_print': auto_print,
        },
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


def _produtos_imobilizado_filtrados(
    empresa_id: int,
    *,
    busca: str = '',
    filtro_setor: str = '',
    somente_saldo: bool = False,
):
    produtos = (
        ProdutoEstoque.objects.filter(
            empresa_id=empresa_id,
            natureza=NaturezaEstoque.IMOBILIZADO,
        )
        .select_related('fornecedor')
        .order_by('setor_localizacao', 'codigo_produto', 'descricao')
    )
    if somente_saldo:
        produtos = produtos.filter(quantidade_estoque__gt=0)
    if filtro_setor == '__sem__':
        produtos = produtos.filter(Q(setor_localizacao='') | Q(setor_localizacao__isnull=True))
    elif filtro_setor:
        produtos = produtos.filter(setor_localizacao=filtro_setor)
    if busca:
        produtos = produtos.filter(
            Q(codigo_produto__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(marca__icontains=busca),
        )
    return produtos


def _historico_linhas_produto(produto: ProdutoEstoque) -> list[dict]:
    linhas: list[dict] = []
    for e in produto.entradas_nota.all():
        nf = e.nota_item.nota_fiscal
        linhas.append(
            {
                'data': e.criado_em,
                'tipo': 'Entrada NF',
                'referencia': f'NF {nf.numero_nota}' if nf else 'NF',
                'fornecedor_nf': (nf.fornecedor_nome if nf else '') or '',
                'quantidade': e.quantidade,
                'valor_unitario': e.valor_unitario,
                'observacao': (e.data_validade.strftime('%d/%m/%Y') if e.data_validade else ''),
            },
        )
    for m in produto.movimentos.all():
        if m.tipo == MovimentoEstoque.Tipo.ENTRADA_NF:
            continue
        origem = m.setor_origem or '—'
        destino = m.setor_destino or '—'
        linhas.append(
            {
                'data': m.criado_em,
                'tipo': m.get_tipo_display(),
                'referencia': f'{origem} → {destino}',
                'fornecedor_nf': '',
                'quantidade': m.quantidade,
                'valor_unitario': m.valor_unitario,
                'observacao': (m.observacao or '')[:120],
            },
        )
    linhas.sort(key=lambda row: row['data'], reverse=True)
    return linhas


def _agrupar_imobilizado_por_setor(produtos) -> list[dict]:
    """Agrupa produtos imobilizado por setor_localizacao (ordem dos setores cadastrados)."""
    por_setor: dict[str, list] = {}
    for p in produtos:
        chave = (p.setor_localizacao or '').strip()
        por_setor.setdefault(chave, []).append(p)

    rotulos = dict(SETOR_LOCALIZACAO_IMOBILIZADO)
    grupos: list[dict] = []
    usados: set[str] = set()

    for val, rotulo in SETOR_LOCALIZACAO_IMOBILIZADO:
        if val not in por_setor:
            continue
        grupos.append({'setor_val': val, 'setor_rotulo': rotulo, 'produtos': por_setor[val]})
        usados.add(val)

    if '' in por_setor:
        grupos.append(
            {
                'setor_val': '',
                'setor_rotulo': 'Sem setor definido',
                'produtos': por_setor[''],
            },
        )
        usados.add('')

    for chave, itens in por_setor.items():
        if chave in usados:
            continue
        grupos.append(
            {
                'setor_val': chave,
                'setor_rotulo': rotulos.get(chave, chave),
                'produtos': itens,
            },
        )

    return grupos


def _agrupar_farmacia_por_setor(
    produtos,
    *,
    filtro_setor: str = '',
    somente_saldo: bool = False,
) -> list[dict]:
    """Agrupa consumíveis por setor (depósito farmácia + saldos clínicos)."""
    from decimal import Decimal

    grupos: list[dict] = []

    def _append(setor_val: str, setor_rotulo: str, produto: ProdutoEstoque, quantidade) -> None:
        for g in grupos:
            if g['setor_val'] == setor_val:
                g['linhas'].append({'produto': produto, 'quantidade': quantidade})
                return
        grupos.append(
            {
                'setor_val': setor_val,
                'setor_rotulo': setor_rotulo,
                'linhas': [{'produto': produto, 'quantidade': quantidade}],
            },
        )

    for setor_val, setor_rotulo in SETOR_LISTA_CEGA_FARMACIA:
        if filtro_setor and filtro_setor != setor_val:
            continue

        if setor_val == SetorEstoque.FARMACIA:
            for p in produtos:
                qtd = p.quantidade_estoque or Decimal('0')
                if somente_saldo and qtd <= 0:
                    continue
                _append(setor_val, setor_rotulo, p, qtd)
            continue

        for p in produtos:
            qtd = None
            for saldo in p.saldos_setor.all():
                if saldo.setor == setor_val:
                    qtd = saldo.quantidade or Decimal('0')
                    break
            if qtd is None:
                continue
            if somente_saldo and qtd <= 0:
                continue
            _append(setor_val, setor_rotulo, p, qtd)

    for g in grupos:
        g['linhas'].sort(key=lambda row: (row['produto'].descricao or '', row['produto'].codigo_produto))
    return [g for g in grupos if g['linhas']]


@login_required
def lista_farmacia_por_setor(request):
    """Relação da farmácia agrupada por setor (qtd no setor + preço médio)."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:farmacia_list')

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    somente_saldo = (request.GET.get('somente_saldo') or '').strip() in ('1', 'true', 'sim')
    filtro_setor = (request.GET.get('setor') or '').strip()
    busca = (request.GET.get('q') or '').strip()

    saldo_qs = SaldoEstoqueSetor.objects.order_by('setor')
    if somente_saldo:
        saldo_qs = saldo_qs.filter(quantidade__gt=0)

    produtos = (
        ProdutoEstoque.objects.filter(
            empresa_id=empresa_id,
            natureza=NaturezaEstoque.CONSUMIVEL,
        )
        .select_related('fornecedor')
        .prefetch_related(Prefetch('saldos_setor', queryset=saldo_qs))
        .order_by('codigo_produto', 'descricao')
    )
    if busca:
        produtos = produtos.filter(
            Q(codigo_produto__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(marca__icontains=busca),
        )

    grupos = _agrupar_farmacia_por_setor(
        list(produtos),
        filtro_setor=filtro_setor,
        somente_saldo=somente_saldo,
    )
    total_linhas = sum(len(g['linhas']) for g in grupos)
    auto_print = (request.GET.get('auto') or '').strip() == '1'

    return render(
        request,
        'estoque/farmacia_lista_setores.html',
        {
            'empresa': empresa,
            'grupos': grupos,
            'busca': busca,
            'filtro_setor': filtro_setor,
            'somente_saldo': somente_saldo,
            'setores_farmacia': SETOR_LISTA_CEGA_FARMACIA,
            'total_linhas': total_linhas,
            'agora': timezone.now(),
            'auto_print': auto_print,
        },
    )


@login_required
def lista_imobilizado_por_setor(request):
    """Relação de imobilizado agrupada por setor (com quantidades e preço médio)."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:imobilizado_list')

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    somente_saldo = (request.GET.get('somente_saldo') or '').strip() in ('1', 'true', 'sim')
    filtro_setor = (request.GET.get('setor') or '').strip()
    busca = (request.GET.get('q') or '').strip()
    produtos = _produtos_imobilizado_filtrados(
        empresa_id,
        busca=busca,
        filtro_setor=filtro_setor,
        somente_saldo=somente_saldo,
    )
    grupos = _agrupar_imobilizado_por_setor(list(produtos))
    total_itens = sum(len(g['produtos']) for g in grupos)
    auto_print = (request.GET.get('auto') or '').strip() == '1'

    return render(
        request,
        'estoque/imobilizado_lista_setores.html',
        {
            'empresa': empresa,
            'grupos': grupos,
            'busca': busca,
            'filtro_setor': filtro_setor,
            'somente_saldo': somente_saldo,
            'setores_imobilizado': SETOR_LOCALIZACAO_IMOBILIZADO,
            'total_itens': total_itens,
            'agora': timezone.now(),
            'auto_print': auto_print,
        },
    )


@login_required
def lista_imobilizado_por_historico(request):
    """Imobilizado: um bloco por produto (resumo + linhas de histórico NF/movimentos)."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:imobilizado_list')

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    somente_saldo = (request.GET.get('somente_saldo') or '').strip() in ('1', 'true', 'sim')
    filtro_setor = (request.GET.get('setor') or '').strip()
    busca = (request.GET.get('q') or '').strip()

    produtos = _produtos_imobilizado_filtrados(
        empresa_id,
        busca=busca,
        filtro_setor=filtro_setor,
        somente_saldo=somente_saldo,
    ).prefetch_related(
        Prefetch(
            'entradas_nota',
            queryset=EntradaEstoqueNota.objects.select_related(
                'nota_item__nota_fiscal',
                'criado_por',
            ).order_by('-criado_em'),
        ),
        Prefetch(
            'movimentos',
            queryset=MovimentoEstoque.objects.select_related('usuario', 'requisicao').order_by(
                '-criado_em',
            ),
        ),
    )

    blocos = []
    for p in produtos:
        blocos.append(
            {
                'produto': p,
                'historico': _historico_linhas_produto(p),
            },
        )

    auto_print = (request.GET.get('auto') or '').strip() == '1'

    return render(
        request,
        'estoque/imobilizado_lista_historico.html',
        {
            'empresa': empresa,
            'blocos': blocos,
            'busca': busca,
            'filtro_setor': filtro_setor,
            'somente_saldo': somente_saldo,
            'setores_imobilizado': SETOR_LOCALIZACAO_IMOBILIZADO,
            'total_itens': len(blocos),
            'agora': timezone.now(),
            'auto_print': auto_print,
        },
    )


@login_required
def lista_cega_estoque(request):
    """Lista para contagem física — sem saldo do sistema."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('estoque:farmacia_list')

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    tipo = (request.GET.get('tipo') or 'farmacia').strip().lower()
    if tipo == 'imobilizado':
        natureza = NaturezaEstoque.IMOBILIZADO
        titulo = 'Lista cega de estoque — Imobilizado'
        voltar_url = reverse('estoque:imobilizado_list')
    else:
        natureza = NaturezaEstoque.CONSUMIVEL
        titulo = 'Lista cega de estoque — Farmácia'
        voltar_url = reverse('estoque:farmacia_list')

    produtos = (
        ProdutoEstoque.objects.filter(empresa_id=empresa_id, natureza=natureza)
        .select_related('fornecedor')
        .order_by('codigo_produto', 'descricao')
    )

    somente_saldo = (request.GET.get('somente_saldo') or '').strip() in ('1', 'true', 'sim')
    filtro_setor = (request.GET.get('setor') or '').strip()

    if natureza == NaturezaEstoque.CONSUMIVEL and filtro_setor:
        if filtro_setor == SetorEstoque.FARMACIA:
            if somente_saldo:
                produtos = produtos.filter(quantidade_estoque__gt=0)
        else:
            saldo_qs = SaldoEstoqueSetor.objects.filter(
                produto__empresa_id=empresa_id,
                setor=filtro_setor,
            )
            if somente_saldo:
                saldo_qs = saldo_qs.filter(quantidade__gt=0)
            produtos = produtos.filter(pk__in=saldo_qs.values_list('produto_id', flat=True)).distinct()
    elif somente_saldo:
        produtos = produtos.filter(quantidade_estoque__gt=0)

    if natureza == NaturezaEstoque.IMOBILIZADO and filtro_setor == '__sem__':
        produtos = produtos.filter(Q(setor_localizacao='') | Q(setor_localizacao__isnull=True))
    elif natureza == NaturezaEstoque.IMOBILIZADO and filtro_setor:
        produtos = produtos.filter(setor_localizacao=filtro_setor)

    setor_coluna_rotulo = ''
    if filtro_setor:
        setor_coluna_rotulo = dict(SetorEstoque.choices).get(filtro_setor, filtro_setor)

    busca = (request.GET.get('q') or '').strip()
    if busca:
        produtos = produtos.filter(
            Q(codigo_produto__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(marca__icontains=busca),
        )

    auto_print = (request.GET.get('auto') or '').strip() == '1'

    return render(
        request,
        'estoque/lista_cega_estoque.html',
        {
            'empresa': empresa,
            'titulo': titulo,
            'tipo': tipo,
            'produtos': produtos,
            'busca': busca,
            'filtro_setor': filtro_setor,
            'somente_saldo': somente_saldo,
            'setores_imobilizado': SETOR_LOCALIZACAO_IMOBILIZADO,
            'setores_farmacia': SETOR_LISTA_CEGA_FARMACIA,
            'setor_coluna_rotulo': setor_coluna_rotulo,
            'voltar_url': voltar_url,
            'agora': timezone.now(),
            'auto_print': auto_print,
        },
    )
