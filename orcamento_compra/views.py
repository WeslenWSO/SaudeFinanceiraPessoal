from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from fornecedor.models import Fornecedor
from orcamento_compra.services.produtos_comercio import (
    dados_produto_comercio,
    listar_produtos_comercio_distintos,
    serializar_produto_comercio,
)
from orcamento_compra.models import (
    OrcamentoCompra,
    OrcamentoCompraFornecedor,
    OrcamentoCompraItem,
    OrcamentoCompraPreco,
)
from orcamento_compra.models import OrcamentoCompraResultadoVencedor
from orcamento_compra.services.pdf_orcamento import extrair_texto_pdf
from orcamento_compra.services.vinculo_pdf import aplicar_vinculos_pdf, atualizar_linhas_do_texto
from orcamento_compra.services.vencedor import gerar_orcamentos_vencedores, vencedor_por_item


def _empresa_id(request):
    return request.session.get('empresa_id')


def _orcamento_empresa(request, pk: int) -> OrcamentoCompra:
    empresa_id = _empresa_id(request)
    return get_object_or_404(OrcamentoCompra, pk=pk, empresa_id=empresa_id)


def _parse_decimal(valor) -> Decimal | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def _decimal_input(valor) -> str:
    if valor is None:
        return ''
    return f'{Decimal(str(valor)):f}'.rstrip('0').rstrip('.').replace('.', ',')


def _moeda_br(valor) -> str:
    if valor is None:
        return '—'
    try:
        v = Decimal(str(valor))
    except Exception:
        return '—'
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _montar_matriz(orcamento: OrcamentoCompra) -> dict:
    itens = list(orcamento.itens.select_related('produto').all())
    colunas = list(orcamento.fornecedores.select_related('fornecedor').all())
    precos = {
        (p.item_id, p.coluna_fornecedor_id): p
        for p in OrcamentoCompraPreco.objects.filter(item__orcamento=orcamento).select_related(
            'item', 'coluna_fornecedor'
        )
    }

    mapa_vencedor = {row['item'].pk: row for row in vencedor_por_item(orcamento)}

    linhas = []
    for item in itens:
        venc = mapa_vencedor.get(item.pk)
        celulas = []
        totais_linha: list[Decimal] = []
        for col in colunas:
            preco = precos.get((item.pk, col.pk))
            unit = preco.preco_unitario if preco else None
            total = preco.total_calculado() if preco else None
            if total is not None:
                totais_linha.append(total)
            celulas.append({
                'coluna_id': col.pk,
                'preco_id': preco.pk if preco else None,
                'preco_unitario': unit,
                'preco_unitario_input': _decimal_input(unit),
                'preco_total_input': _decimal_input(preco.preco_total if preco and preco.preco_total is not None else None),
                'preco_total': total,
                'preco_total_fmt': _moeda_br(total) if total is not None else '',
                'observacao': (preco.observacao if preco else '') or '',
            })
        menor = min(totais_linha) if totais_linha else None
        linhas.append({
            'item': item,
            'celulas': celulas,
            'menor_total': menor,
            'vencedor_coluna_id': venc['coluna'].pk if venc else None,
            'vencedor_nome': venc['coluna'].nome_exibicao if venc else '',
        })

    totais_coluna = []
    for idx, col in enumerate(colunas):
        soma = Decimal('0')
        tem = False
        for linha in linhas:
            t = linha['celulas'][idx]['preco_total']
            if t is not None:
                soma += t
                tem = True
        totais_coluna.append({
            'coluna_id': col.pk,
            'total_fmt': _moeda_br(soma) if tem else '—',
            'total': soma if tem else None,
        })

    return {
        'linhas': linhas,
        'colunas': colunas,
        'totais_coluna': totais_coluna,
    }


@login_required
@require_GET
def listar(request):
    empresa_id = _empresa_id(request)
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    qs = OrcamentoCompra.objects.filter(empresa_id=empresa_id).order_by('-atualizado_em')
    return render(request, 'orcamento_compra/lista.html', {'orcamentos': qs})


@login_required
@require_POST
def criar(request):
    empresa_id = _empresa_id(request)
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    titulo = (request.POST.get('titulo') or '').strip()
    if not titulo:
        messages.error(request, 'Informe o título do orçamento.')
        return redirect('orcamento_compra:listar')
    obs = (request.POST.get('observacao') or '').strip()
    orc = OrcamentoCompra.objects.create(
        empresa_id=empresa_id,
        titulo=titulo,
        observacao=obs,
        status=OrcamentoCompra.STATUS_COTACAO,
        criado_por=request.user,
    )
    messages.success(request, 'Orçamento criado. Adicione produtos e fornecedores.')
    return redirect('orcamento_compra:detalhe', pk=orc.pk)


@login_required
@require_GET
def detalhe(request, pk: int):
    empresa_id = _empresa_id(request)
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    orcamento = _orcamento_empresa(request, pk)
    matriz = _montar_matriz(orcamento)
    fornecedores = Fornecedor.objects.filter(empresa_id=empresa_id).order_by('razao')[:500]
    resultados_qs = (
        OrcamentoCompraResultadoVencedor.objects.filter(orcamento=orcamento)
        .select_related('coluna_fornecedor', 'coluna_fornecedor__fornecedor')
        .prefetch_related('itens')
        .order_by('coluna_fornecedor__ordem')
    )
    resultados = [
        {
            'obj': res,
            'total_fmt': _moeda_br(res.total_geral),
            'qtd_itens': len(res.itens.all()),
        }
        for res in resultados_qs
    ]
    preview_vencedores = vencedor_por_item(orcamento)
    itens_orcamento = list(orcamento.itens.order_by('ordem', 'id'))
    return render(
        request,
        'orcamento_compra/detalhe.html',
        {
            'orcamento': orcamento,
            'itens_orcamento': itens_orcamento,
            'matriz': matriz,
            'fornecedores_cadastro': fornecedores,
            'status_choices': OrcamentoCompra.STATUS_CHOICES,
            'resultados_vencedores': resultados,
            'pode_gerar_vencedor': bool(preview_vencedores),
            'qtd_itens_com_vencedor': len(preview_vencedores),
        },
    )


@login_required
@require_POST
def excluir(request, pk: int):
    orcamento = _orcamento_empresa(request, pk)
    orcamento.delete()
    messages.success(request, 'Orçamento excluído.')
    return redirect('orcamento_compra:listar')


@login_required
@require_POST
def atualizar_cabecalho(request, pk: int):
    orcamento = _orcamento_empresa(request, pk)
    titulo = (request.POST.get('titulo') or '').strip()
    if titulo:
        orcamento.titulo = titulo
    orcamento.observacao = (request.POST.get('observacao') or '').strip()
    status = (request.POST.get('status') or '').strip()
    if status in dict(OrcamentoCompra.STATUS_CHOICES):
        orcamento.status = status
    orcamento.save(update_fields=['titulo', 'observacao', 'status', 'atualizado_em'])
    messages.success(request, 'Orçamento atualizado.')
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_GET
def buscar_produto_comercio_ajax(request, pk: int):
    """JSON: busca produtos NF comércio por código exato ou descrição."""
    empresa_id = _empresa_id(request)
    if not empresa_id:
        return JsonResponse({'ok': False, 'error': 'Empresa não selecionada.'}, status=400)
    _orcamento_empresa(request, pk)
    q = (request.GET.get('q') or '').strip()
    codigo_exato = request.GET.get('codigo_exato') == '1'
    if codigo_exato:
        if not q:
            return JsonResponse({'ok': False, 'error': 'Informe o código.'}, status=400)
        dados = dados_produto_comercio(empresa_id, q)
        if not dados:
            return JsonResponse({'ok': False, 'error': 'Código não encontrado na NF comércio.'}, status=404)
        return JsonResponse({'ok': True, 'itens': [serializar_produto_comercio(dados)]})
    if len(q) < 2:
        return JsonResponse({'ok': True, 'itens': []})
    itens = listar_produtos_comercio_distintos(empresa_id, busca=q, limite=25)
    return JsonResponse({
        'ok': True,
        'itens': [serializar_produto_comercio(i) for i in itens],
    })


@login_required
@require_POST
def adicionar_item(request, pk: int):
    orcamento = _orcamento_empresa(request, pk)
    empresa_id = _empresa_id(request)
    codigo_comercio = (request.POST.get('produto_comercio_codigo') or '').strip()
    descricao = (request.POST.get('descricao') or '').strip()
    quantidade = _parse_decimal(request.POST.get('quantidade')) or Decimal('1')
    unidade = 'UN'
    codigo_gravado = ''
    if codigo_comercio:
        dados = dados_produto_comercio(empresa_id, codigo_comercio)
        if not dados:
            messages.error(request, 'Produto de NF comércio não encontrado para este código.')
            return redirect('orcamento_compra:detalhe', pk=pk)
        codigo_gravado = dados['codigo']
        if not descricao:
            descricao = dados['nome']
        unidade = dados['unidade']
    if not descricao:
        messages.error(request, 'Selecione um produto de NF comércio ou informe a descrição.')
        return redirect('orcamento_compra:detalhe', pk=pk)
    max_ordem = orcamento.itens.order_by('-ordem').values_list('ordem', flat=True).first() or 0
    item = OrcamentoCompraItem.objects.create(
        orcamento=orcamento,
        produto=None,
        codigo_produto_comercio=codigo_gravado,
        descricao=descricao,
        unidade=unidade,
        quantidade=quantidade,
        ordem=max_ordem + 1,
    )
    for col in orcamento.fornecedores.all():
        OrcamentoCompraPreco.objects.get_or_create(item=item, coluna_fornecedor=col)
    messages.success(request, 'Item adicionado.')
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_POST
def adicionar_fornecedor(request, pk: int):
    orcamento = _orcamento_empresa(request, pk)
    empresa_id = _empresa_id(request)
    fornecedor_id = request.POST.get('fornecedor_id')
    nome = (request.POST.get('nome_exibicao') or '').strip()
    fornecedor = None
    if fornecedor_id:
        fornecedor = Fornecedor.objects.filter(pk=fornecedor_id, empresa_id=empresa_id).first()
        if fornecedor and not nome:
            nome = fornecedor.razao
    if not nome:
        messages.error(request, 'Informe o fornecedor ou o nome da coluna.')
        return redirect('orcamento_compra:detalhe', pk=pk)
    max_ordem = orcamento.fornecedores.order_by('-ordem').values_list('ordem', flat=True).first() or 0
    col = OrcamentoCompraFornecedor.objects.create(
        orcamento=orcamento,
        fornecedor=fornecedor,
        nome_exibicao=nome,
        ordem=max_ordem + 1,
    )
    for item in orcamento.itens.all():
        OrcamentoCompraPreco.objects.get_or_create(item=item, coluna_fornecedor=col)
    messages.success(request, 'Fornecedor adicionado à comparação.')
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_POST
def excluir_item(request, pk: int, item_id: int):
    orcamento = _orcamento_empresa(request, pk)
    item = get_object_or_404(OrcamentoCompraItem, pk=item_id, orcamento=orcamento)
    item.delete()
    messages.success(request, 'Item removido.')
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_POST
def excluir_fornecedor(request, pk: int, coluna_id: int):
    orcamento = _orcamento_empresa(request, pk)
    col = get_object_or_404(OrcamentoCompraFornecedor, pk=coluna_id, orcamento=orcamento)
    col.delete()
    messages.success(request, 'Coluna do fornecedor removida.')
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_POST
def upload_pdf_fornecedor(request, pk: int, coluna_id: int):
    import logging
    from io import BytesIO

    from django.core.files.base import ContentFile

    logger = logging.getLogger(__name__)
    orcamento = _orcamento_empresa(request, pk)
    col = get_object_or_404(OrcamentoCompraFornecedor, pk=coluna_id, orcamento=orcamento)
    arquivo = request.FILES.get('pdf_orcamento')
    if not arquivo:
        messages.error(request, 'Selecione um arquivo PDF.')
        return redirect('orcamento_compra:detalhe', pk=pk)

    try:
        buffer = BytesIO()
        for chunk in arquivo.chunks():
            buffer.write(chunk)
        data = buffer.getvalue()
        if not data:
            messages.error(request, 'O arquivo enviado está vazio.')
            return redirect('orcamento_compra:detalhe', pk=pk)
        if len(data) > 50 * 1024 * 1024:
            messages.error(request, 'PDF muito grande. Tamanho máximo: 50 MB.')
            return redirect('orcamento_compra:detalhe', pk=pk)

        nome = (arquivo.name or 'orcamento.pdf').replace('\\', '/').split('/')[-1].strip()
        if not nome.lower().endswith('.pdf'):
            messages.warning(request, 'Extensão incomum; o arquivo será salvo como PDF.')
            if '.' not in nome:
                nome = f'{nome}.pdf'

        texto = extrair_texto_pdf(BytesIO(data))

        if col.pdf_orcamento:
            try:
                col.pdf_orcamento.delete(save=False)
            except Exception:
                logger.exception('Não foi possível remover PDF anterior do fornecedor %s', col.pk)

        col.pdf_orcamento.save(nome, ContentFile(data), save=False)
        col.pdf_texto = texto
        col.pdf_linhas = atualizar_linhas_do_texto(col) if texto.strip() else []
        col.save(update_fields=['pdf_orcamento', 'pdf_texto', 'pdf_linhas'])

        if texto.strip() and col.pdf_linhas:
            messages.success(
                request,
                f'PDF importado — {len(col.pdf_linhas)} linha(s) detectada(s). '
                'Vincule aos produtos do orçamento.',
            )
            return redirect('orcamento_compra:vincular_pdf', pk=pk, coluna_id=coluna_id)
        if texto.strip():
            messages.warning(
                request,
                'PDF importado, mas nenhuma linha com preço foi reconhecida. '
                'Você pode vincular manualmente ou lançar preços na tabela.',
            )
            return redirect('orcamento_compra:vincular_pdf', pk=pk, coluna_id=coluna_id)
        messages.warning(
            request,
            'PDF anexado sem texto extraído (comum em PDF escaneado). '
            'Use o arquivo como referência e digite os valores na tabela.',
        )
    except OSError as exc:
        logger.exception('Erro de armazenamento ao importar PDF orçamento compra')
        messages.error(
            request,
            f'Erro ao gravar o PDF no servidor ({exc}). '
            'Verifique permissões da pasta media (MEDIA_ROOT).',
        )
    except Exception as exc:
        logger.exception('Erro ao importar PDF orçamento compra')
        messages.error(request, f'Erro ao importar PDF: {exc}')

    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_GET
def vincular_pdf(request, pk: int, coluna_id: int):
    orcamento = _orcamento_empresa(request, pk)
    col = get_object_or_404(OrcamentoCompraFornecedor, pk=coluna_id, orcamento=orcamento)
    itens = list(orcamento.itens.order_by('ordem', 'id'))
    linhas = list(col.pdf_linhas or [])
    if not linhas and (col.pdf_texto or '').strip():
        linhas = atualizar_linhas_do_texto(col)
        col.pdf_linhas = linhas
        col.save(update_fields=['pdf_linhas'])

    linhas_view = []
    for linha in linhas:
        item_id = linha.get('item_id')
        try:
            item_id_int = int(item_id) if item_id else None
        except (TypeError, ValueError):
            item_id_int = None
        total_dec = _parse_decimal(linha.get('preco_total'))
        linhas_view.append({
            'idx': linha.get('idx', 0),
            'descricao': linha.get('descricao') or '',
            'preco_total_fmt': _moeda_br(total_dec) if total_dec is not None else '—',
            'item_id': item_id_int,
        })

    return render(
        request,
        'orcamento_compra/vincular_pdf.html',
        {
            'orcamento': orcamento,
            'coluna': col,
            'itens': itens,
            'linhas': linhas_view,
            'tem_pdf': bool(col.pdf_orcamento),
        },
    )


@login_required
@require_POST
def salvar_vinculo_pdf(request, pk: int, coluna_id: int):
    orcamento = _orcamento_empresa(request, pk)
    col = get_object_or_404(OrcamentoCompraFornecedor, pk=coluna_id, orcamento=orcamento)
    linhas = list(col.pdf_linhas or [])
    if not linhas and (col.pdf_texto or '').strip():
        linhas = atualizar_linhas_do_texto(col)

    if request.POST.get('reprocessar') == '1':
        linhas = atualizar_linhas_do_texto(col)
        col.pdf_linhas = linhas
        col.save(update_fields=['pdf_linhas'])
        messages.info(request, 'Linhas do PDF reprocessadas.')
        return redirect('orcamento_compra:vincular_pdf', pk=pk, coluna_id=coluna_id)

    for linha in linhas:
        idx = linha.get('idx')
        key = f'item_{idx}'
        raw = (request.POST.get(key) or '').strip()
        linha['item_id'] = int(raw) if raw.isdigit() else None

    vinculos, precos = aplicar_vinculos_pdf(col, linhas)
    messages.success(
        request,
        f'Vínculo salvo: {vinculos} produto(s) ligado(s), {precos} preço(s) atualizado(s) na comparação.',
    )
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_POST
def salvar_item_ajax(request, pk: int, item_id: int):
    orcamento = _orcamento_empresa(request, pk)
    item = get_object_or_404(OrcamentoCompraItem, pk=item_id, orcamento=orcamento)
    descricao = (request.POST.get('descricao') or '').strip()
    if descricao:
        item.descricao = descricao
    qtd = _parse_decimal(request.POST.get('quantidade'))
    if qtd is not None and qtd > 0:
        item.quantidade = qtd
    unidade = (request.POST.get('unidade') or '').strip()
    if unidade:
        item.unidade = unidade
    item.save(update_fields=['descricao', 'quantidade', 'unidade'])
    return JsonResponse({
        'ok': True,
        'descricao': item.descricao,
        'quantidade': str(item.quantidade),
        'unidade': item.unidade,
    })


@login_required
@require_POST
def salvar_preco_ajax(request, pk: int):
    orcamento = _orcamento_empresa(request, pk)
    try:
        item_id = int(request.POST.get('item_id') or 0)
        coluna_id = int(request.POST.get('coluna_id') or 0)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Dados inválidos.'}, status=400)
    item = get_object_or_404(OrcamentoCompraItem, pk=item_id, orcamento=orcamento)
    col = get_object_or_404(OrcamentoCompraFornecedor, pk=coluna_id, orcamento=orcamento)
    preco, _ = OrcamentoCompraPreco.objects.get_or_create(item=item, coluna_fornecedor=col)
    unit = _parse_decimal(request.POST.get('preco_unitario'))
    total = _parse_decimal(request.POST.get('preco_total'))
    if request.POST.get('preco_unitario', '').strip() == '':
        unit = None
    if request.POST.get('preco_total', '').strip() == '':
        total = None
    preco.preco_unitario = unit
    preco.preco_total = total
    preco.observacao = (request.POST.get('observacao') or '').strip()[:255]
    preco.save(update_fields=['preco_unitario', 'preco_total', 'observacao'])
    calc = preco.total_calculado()
    return JsonResponse({
        'ok': True,
        'preco_unitario_fmt': _moeda_br(unit) if unit is not None else '',
        'preco_total_fmt': _moeda_br(calc) if calc is not None else '',
    })


@login_required
@require_POST
def gerar_vencedores(request, pk: int):
    orcamento = _orcamento_empresa(request, pk)
    preview = vencedor_por_item(orcamento)
    if not preview:
        messages.error(
            request,
            'Não há preços suficientes para definir vencedores. Lance valores na tabela de comparação.',
        )
        return redirect('orcamento_compra:detalhe', pk=pk)
    criados = gerar_orcamentos_vencedores(orcamento)
    if not criados:
        messages.warning(request, 'Nenhum fornecedor ficou com itens vencedores.')
    else:
        messages.success(
            request,
            f'Gerados {len(criados)} orçamento(s) vencedor(es) — um por fornecedor com itens ganhos.',
        )
    return redirect('orcamento_compra:detalhe', pk=pk)


@login_required
@require_GET
def imprimir_vencedor(request, pk: int, resultado_id: int):
    empresa_id = _empresa_id(request)
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')
    orcamento = _orcamento_empresa(request, pk)
    resultado = get_object_or_404(
        OrcamentoCompraResultadoVencedor,
        pk=resultado_id,
        orcamento=orcamento,
    )
    from empresa.models import Empresa

    empresa = Empresa.objects.filter(pk=empresa_id).first()
    itens_raw = list(resultado.itens.all())
    col = resultado.coluna_fornecedor
    fornecedor = col.fornecedor
    itens = [
        {
            'obj': it,
            'unit_fmt': _moeda_br(it.preco_unitario),
            'total_fmt': _moeda_br(it.preco_total),
        }
        for it in itens_raw
    ]
    return render(
        request,
        'orcamento_compra/imprimir_vencedor.html',
        {
            'orcamento': orcamento,
            'resultado': resultado,
            'empresa': empresa,
            'coluna': col,
            'fornecedor': fornecedor,
            'itens': itens,
            'total_fmt': _moeda_br(resultado.total_geral),
            'gerado_em_fmt': resultado.gerado_em.strftime('%d/%m/%Y %H:%M'),
        },
    )
