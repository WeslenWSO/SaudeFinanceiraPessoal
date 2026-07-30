from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from empresa.models import Empresa, UsuarioEmpresa

from .agrupamento import agrupar_itens_por_cartao, resumir_parcelas_futuras, resumir_por_fornecedor, resumo_cartoes_fatura
from .categorias import LEGENDA_CATEGORIAS, LEGENDA_POR_SLUG, NOTA_TRANSACOES_EXTERIOR, enriquecer_perfil_consumo
from .forms import CartaoCreditoForm, ImportarFaturaCartaoForm
from .fatura_pdf import detectar_banco_fatura_pdf, parse_fatura_cartao_pdf
from .models import CartaoCredito, FaturaCartaoCredito, ItemFaturaCartao
from .sicredi_pdf import parse_fatura_sicredi_pdf
from .sicoob_pdf import parse_fatura_sicoob_pdf


def _empresa_da_sessao(request):
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        return Empresa.objects.get(id=empresa_id)
    usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
    if not usuario_empresa:
        usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
    if not usuario_empresa:
        raise Empresa.DoesNotExist
    return usuario_empresa.empresa


def _parse_arquivo_fatura(arquivo, banco_escolhido: str):
    if banco_escolhido == 'SICREDI':
        return parse_fatura_sicredi_pdf(arquivo)
    if banco_escolhido == 'SICOOB':
        return parse_fatura_sicoob_pdf(arquivo)
    return parse_fatura_cartao_pdf(arquivo)


def _codigo_banco(dados: dict) -> str:
    nome = (dados.get('banco') or '').upper()
    if 'SICOOB' in nome:
        return 'SICOOB'
    return 'SICREDI'


@login_required
def cartao_listar(request):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    cartoes = CartaoCredito.objects.filter(empresa=empresa)
    return render(request, 'OPCARTAO/cartao_listar.html', {
        'cartoes': cartoes,
        'empresa': empresa,
    })


@login_required
def cartao_novo(request):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    if request.method == 'POST':
        form = CartaoCreditoForm(request.POST)
        if form.is_valid():
            cartao = form.save(commit=False)
            cartao.empresa = empresa
            cartao.save()
            messages.success(request, 'Cartão cadastrado com sucesso.')
            return redirect('opcartao:cartao_listar')
    else:
        form = CartaoCreditoForm()

    return render(request, 'OPCARTAO/cartao_form.html', {'form': form, 'titulo': 'Novo cartão'})


@login_required
def cartao_editar(request, pk):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    cartao = get_object_or_404(CartaoCredito, pk=pk, empresa=empresa)
    if request.method == 'POST':
        form = CartaoCreditoForm(request.POST, instance=cartao)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cartão atualizado.')
            return redirect('opcartao:cartao_listar')
    else:
        form = CartaoCreditoForm(instance=cartao)

    return render(request, 'OPCARTAO/cartao_form.html', {
        'form': form,
        'titulo': 'Editar cartão',
        'cartao': cartao,
    })


@login_required
def cartao_excluir(request, pk):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    cartao = get_object_or_404(CartaoCredito, pk=pk, empresa=empresa)
    if request.method == 'POST':
        cartao.delete()
        messages.success(request, 'Cartão excluído.')
        return redirect('opcartao:cartao_listar')
    return render(request, 'OPCARTAO/cartao_excluir.html', {'cartao': cartao})


@login_required
def fatura_listar(request):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    faturas = FaturaCartaoCredito.objects.filter(empresa=empresa).select_related('cartao').prefetch_related('itens')
    return render(request, 'OPCARTAO/fatura_listar.html', {
        'faturas': faturas,
        'empresa': empresa,
    })


@login_required
def fatura_importar(request):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    if request.method == 'POST':
        form = ImportarFaturaCartaoForm(request.POST, request.FILES, empresa=empresa)
        if form.is_valid():
            arquivo = form.cleaned_data['arquivo']
            banco_escolhido = form.cleaned_data.get('banco') or ''
            cartao = form.cleaned_data.get('cartao')
            try:
                dados = _parse_arquivo_fatura(arquivo, banco_escolhido)
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, 'OPCARTAO/fatura_importar.html', {'form': form})
            except Exception as exc:
                messages.error(request, f'Erro ao ler o PDF: {exc}')
                return render(request, 'OPCARTAO/fatura_importar.html', {'form': form})

            if not dados.get('itens'):
                banco_detectado = detectar_banco_fatura_pdf(arquivo)
                messages.warning(
                    request,
                    f'Nenhuma transação encontrada no PDF ({banco_detectado or "formato desconhecido"}). '
                    'Verifique se é uma fatura Sicredi ou Sicoob válida.',
                )
                return render(request, 'OPCARTAO/fatura_importar.html', {'form': form})

            banco = _codigo_banco(dados)
            vencimento = dados.get('vencimento')
            cartao_final = dados.get('cartao_final', '') or (cartao.final_cartao if cartao else '')
            duplicada = FaturaCartaoCredito.objects.filter(
                empresa=empresa,
                banco=banco,
                vencimento=vencimento,
                cartao_final=cartao_final,
                total_fatura=dados.get('total_fatura'),
            ).exists()
            if duplicada:
                messages.warning(
                    request,
                    'Já existe uma fatura importada com o mesmo vencimento, cartão e valor total.',
                )
                return redirect('opcartao:fatura_listar')

            bandeira = dados.get('bandeira', '')
            if cartao and cartao.bandeira:
                bandeira = cartao.get_bandeira_display()

            with transaction.atomic():
                fatura = FaturaCartaoCredito.objects.create(
                    empresa=empresa,
                    cartao=cartao,
                    banco=banco,
                    titular=dados.get('titular', ''),
                    bandeira=bandeira,
                    cartao_final=cartao_final,
                    referencia_mes=dados.get('referencia_mes', ''),
                    vencimento=vencimento,
                    total_fatura=dados.get('total_fatura'),
                    arquivo_nome=arquivo.name,
                    perfil_consumo=dados.get('perfil_consumo') or [],
                    conta_cartao=dados.get('conta_cartao', ''),
                    cartoes_resumo=dados.get('cartoes_resumo') or [],
                )
                itens = [
                    ItemFaturaCartao(
                        fatura=fatura,
                        data=item.get('data'),
                        hora=item.get('hora', ''),
                        cartao_portador=item.get('cartao_portador', ''),
                        cartao_final=item.get('cartao_final', '') or cartao_final,
                        cidade=item.get('cidade', ''),
                        tipo_compra=item.get('tipo_compra', ''),
                        descricao=item.get('descricao', ''),
                        parcela=item.get('parcela', ''),
                        categoria=item.get('categoria', ''),
                        valor=item.get('valor'),
                        tipo=item.get('tipo', 'compra'),
                    )
                    for item in dados['itens']
                ]
                ItemFaturaCartao.objects.bulk_create(itens)

            messages.success(
                request,
                f'Fatura {dados.get("banco", banco)} importada com sucesso: {dados.get("qtd_itens", 0)} lançamentos.',
            )
            return redirect('opcartao:fatura_detalhe', pk=fatura.pk)
    else:
        form = ImportarFaturaCartaoForm(empresa=empresa)

    return render(request, 'OPCARTAO/fatura_importar.html', {'form': form})


@login_required
def fatura_detalhe(request, pk):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    fatura = get_object_or_404(FaturaCartaoCredito, pk=pk, empresa=empresa)
    itens = fatura.itens.all()
    totais = itens.aggregate(
        compras=Sum('valor', filter=Q(tipo='compra')),
        pagamentos=Sum('valor', filter=Q(tipo='pagamento')),
        iof=Sum('valor', filter=Q(tipo='iof')),
    )
    limite_disponivel = None
    if fatura.cartao and fatura.cartao.limite:
        limite_disponivel = fatura.cartao.limite - fatura.total_fatura
    perfil = enriquecer_perfil_consumo(fatura.perfil_consumo or [])
    grupos_cartao = agrupar_itens_por_cartao(fatura)
    itens_list = list(itens)
    resumo_fornecedor = resumir_por_fornecedor(itens_list)
    parcelas_futuras = resumir_parcelas_futuras(itens_list)
    total_lancamentos_compras = sum(r['qtd'] for r in resumo_fornecedor)
    exibir_cartao_parcelas = any(l['cartao_final'] for l in parcelas_futuras['linhas'])
    return render(request, 'OPCARTAO/fatura_detalhe.html', {
        'fatura': fatura,
        'itens': itens,
        'grupos_cartao': grupos_cartao,
        'resumo_fornecedor': resumo_fornecedor,
        'parcelas_futuras': parcelas_futuras,
        'exibir_cartao_parcelas': exibir_cartao_parcelas,
        'total_lancamentos_compras': total_lancamentos_compras,
        'totais': totais,
        'limite_disponivel': limite_disponivel,
        'legenda_categorias': LEGENDA_CATEGORIAS,
        'legenda_por_slug': LEGENDA_POR_SLUG,
        'perfil_consumo': perfil,
        'nota_exterior': NOTA_TRANSACOES_EXTERIOR,
    })


@login_required
def fatura_excluir(request, pk):
    try:
        empresa = _empresa_da_sessao(request)
    except Empresa.DoesNotExist:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:trocar')

    fatura = get_object_or_404(FaturaCartaoCredito, pk=pk, empresa=empresa)
    if request.method == 'POST':
        fatura.delete()
        messages.success(request, 'Fatura excluída.')
        return redirect('opcartao:fatura_listar')
    return render(request, 'OPCARTAO/fatura_excluir.html', {'fatura': fatura})
