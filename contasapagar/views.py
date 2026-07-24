from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from SaudeFinanceira import buscajson
from django.views.decorators.http import require_POST
from .utils import (
    formatar_cpf_cnpj_sicoob,
    processar_pdf_contas_pagar,
    processar_relatorio_liquidos_pdf,
)
from django.db import transaction

from contasapagar.models import ContasaPagar
from categoria.models import Categoria
from fornecedor.models import Fornecedor
from cobranca.models import Cobranca
from extrato.models import ContaBancaria
from regrarateio.models import RegraRateio


def _parse_decimal_br(s, default=None):
    """Converte string numérica pt-BR (vírgula decimal) em Decimal."""
    if s is None or (isinstance(s, str) and not s.strip()):
        return default
    try:
        return Decimal(str(s).strip().replace(',', '.'))
    except InvalidOperation:
        return default


def _regra_rateio_from_post(request, empresa_id=None):
    """Retorna instância de RegraRateio ou None a partir de POST['rateio']."""
    rid = (request.POST.get('rateio') or '').strip()
    if rid.isdigit():
        qs = RegraRateio.objects.filter(pk=int(rid))
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs.first()
    return None


# Create your views here.
def listar_contas_a_pagar(request):
    """Lista todas as contas a pagar com filtros e paginação"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listar')

    # Para contas a pagar, filtrar por fornecedor da empresa
    contas = ContasaPagar.objects.filter(empresa_id=empresa_id).order_by('-dtvenc')

    # Filtros (validação: strip em textos)
    search = (request.GET.get('search') or '').strip()
    status = (request.GET.get('status') or '').strip()
    categoria = (request.GET.get('categoria') or '').strip()
    forma_pagamento = (request.GET.get('forma_pagamento') or '').strip()
    data_inicio = (request.GET.get('data_inicio') or '').strip()
    data_fim = (request.GET.get('data_fim') or '').strip()

    # Paginação
    per_page = request.GET.get('per_page', '25')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100, 150]:
            per_page = 25
    except ValueError:
        per_page = 25

    # Buscar categorias e formas de pagamento
    categorias = Categoria.objects.filter(empresa_id=empresa_id)
    formas_pagamento = Cobranca.objects.all()
    fornecedores = Fornecedor.objects.filter(empresa_id=empresa_id)

    # Definir datas padrão (últimos 12 meses)
    hoje = timezone.now().date()
    data_inicio_padrao = hoje - timedelta(days=365)
    data_fim_padrao = hoje

    # Se não há datas selecionadas, usar as datas padrão
    if not data_inicio:
        data_inicio = data_inicio_padrao.strftime('%Y-%m-%d')
    if not data_fim:
        data_fim = data_fim_padrao.strftime('%Y-%m-%d')
    # Garantir data_inicio <= data_fim (trocar se invertidas)
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    # Aplicar filtros
    if search:
        contas = contas.filter(
            Q(fornecedor__razao__icontains=search) |
            Q(descricao__icontains=search) |
            Q(numdoc__icontains=search)
        )

    if status:
        contas = contas.filter(status=status)

    if categoria:
        contas = contas.filter(categoria_id=categoria)

    if forma_pagamento:
        contas = contas.filter(cobranca_id=forma_pagamento)

    # Sempre aplicar filtro de data (usando datas padrão se não selecionadas)
    contas = contas.filter(dtEmissao__gte=data_inicio)
    contas = contas.filter(dtEmissao__lte=data_fim)

    # Estatísticas baseadas no queryset filtrado (antes da paginação)
    contas_filtradas = list(contas)  # Converter para lista para calcular estatísticas
    total_pendente = sum(conta.get_valor_pendente() for conta in contas_filtradas if conta.status != 'pago')
    total_vencido = sum(conta.get_valor_pendente() for conta in contas_filtradas if conta.is_vencida() and conta.status != 'pago')
    total_pago = sum(conta.valorPago or 0 for conta in contas_filtradas if conta.status == 'pago')
    total_contas_pagar = sum(conta.valorDoc for conta in contas_filtradas)

    # Aplicar paginação
    paginator = Paginator(contas, per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'contas': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'total_pendente': total_pendente,
        'total_vencido': total_vencido,
        'total_pago': total_pago,
        'total_contas_pagar': total_contas_pagar,
        'categorias': categorias,
        'formas_pagamento': formas_pagamento,
        'fornecedores': fornecedores,
        'search': search,
        'status_filter': status,
        'categoria_filter': categoria,
        'forma_pagamento_filter': forma_pagamento,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'per_page': per_page,
        'is_paginated': page_obj.has_other_pages(),
        'filtros': {
            'search': search,
            'status': status,
            'categoria': categoria,
            'forma_pagamento': forma_pagamento,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'per_page': per_page,
        }
    }

    return render(request, 'contaaPagarListar.html', context)

# Manter função antiga para compatibilidade
def contasapagar(request):
    return listar_contas_a_pagar(request)

def detalhes_conta_a_pagar(request, pk):
    """Exibe detalhes de uma conta a pagar"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listar')

    conta = get_object_or_404(ContasaPagar, pk=pk, empresa_id=empresa_id)

    # Capturar parâmetros GET para preservar filtros na navegação
    filtros_query = request.GET.urlencode()

    context = {
        'conta': conta,
        'filtros_query': filtros_query,
    }

    return render(request, 'contasapagar/detalhes.html', context)

@login_required
def detalhes_modal(request, tipo, id):
    """
    View para fornecer dados ao modal de detalhes
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'error': 'Empresa não selecionada'}, status=400)

    try:
        # Buscar o objeto baseado no tipo
        if tipo == 'conta_pagar':
            obj = ContasaPagar.objects.get(id=id, empresa_id=empresa_id)
            conta_pagar = obj
        else:
            return JsonResponse({'error': 'Tipo inválido'}, status=400)

        # Buscar dados relacionados
        # Buscar movimentos do extrato relacionados
        from extrato.models import ExtratoMovimento, Lancamento
        movimentos = ExtratoMovimento.objects.filter(conta_pagar=conta_pagar).order_by('-data_baixa')

        # Buscar lançamentos conciliados
        lancamentos_conciliados = []
        for movimento in movimentos:
            if movimento.lancamento:
                lancamentos_conciliados.append({
                    'data': movimento.lancamento.data.strftime('%d/%m/%Y'),
                    'valor': float(movimento.lancamento.valor),
                    'historico': movimento.lancamento.historico,
                    'documento': movimento.lancamento.documento or '',
                    'banco': movimento.lancamento.conta.banco.nome if movimento.lancamento.conta and movimento.lancamento.conta.banco else 'N/A'
                })

        # Construir HTML do modal
        html = f"""
        <div class="row">
            <div class="col-md-12">
                <h5>Conta a Pagar</h5>
                <p><strong>Fornecedor:</strong> {conta_pagar.fornecedor.razao if conta_pagar.fornecedor else 'N/A'}</p>
                <p><strong>Descrição:</strong> {conta_pagar.descricao}</p>
                <p><strong>Categoria:</strong> {conta_pagar.categoria.nome if conta_pagar.categoria else 'N/A'}</p>
                <p><strong>Valor:</strong> R$ {conta_pagar.valorDoc:.2f}</p>
                <p><strong>Data Emissão:</strong> {conta_pagar.dtEmissao.strftime('%d/%m/%Y') if conta_pagar.dtEmissao else 'N/A'}</p>
                <p><strong>Data Vencimento:</strong> {conta_pagar.dtvenc.strftime('%d/%m/%Y') if conta_pagar.dtvenc else 'N/A'}</p>
                <p><strong>Data Pagamento:</strong> {conta_pagar.dtPag.strftime('%d/%m/%Y') if conta_pagar.dtPag else 'N/A'}</p>
                <p><strong>Status:</strong> {conta_pagar.get_status_display()}</p>
                <p><strong>Documento:</strong> {conta_pagar.numdoc or 'N/A'}</p>
                <p><strong>Cobrança:</strong> {conta_pagar.cobranca.descricao if conta_pagar.cobranca else 'N/A'}</p>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-md-6">
                <h5>Movimentos do Extrato</h5>
                {''.join([f'<p><strong>{m.data_baixa.strftime("%d/%m/%Y")}:</strong> R$ {m.valor:.2f} - {m.descricao[:50]}...</p>' for m in movimentos[:3]]) if movimentos else '<p>Nenhum movimento encontrado</p>'}
            </div>
            <div class="col-md-6">
                <h5>Lançamentos Bancários Conciliados</h5>
                {''.join([f'<p><strong>{l["data"]}:</strong> R$ {l["valor"]:.2f} - {l["historico"][:30]}... ({l["banco"]})</p>' for l in lancamentos_conciliados[:3]]) if lancamentos_conciliados else '<p>Nenhum lançamento conciliado encontrado</p>'}
            </div>
        </div>
        """

        return JsonResponse({'html': html})

    except Exception as e:
        return JsonResponse({'error': f'Erro interno: {str(e)}'}, status=500)

def cadastrar_conta_a_pagar(request):
    """Cadastrar uma nova conta a pagar"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    if request.method == 'POST':
        try:
            # Obter dados do formulário
            fornecedor_id = request.POST.get('fornecedor')
            descricao = request.POST.get('descricao')
            valor_str = request.POST.get('valor')
            # Convert Brazilian decimal format (comma) to Python decimal format (dot)
            if valor_str:
                valor = float(valor_str.replace(',', '.'))
            else:
                valor = 0
            data_emissao = request.POST.get('data_emissao')
            data_vencimento = request.POST.get('data_vencimento')
            categoria_id = request.POST.get('categoria')
            forma_pagamento_id = request.POST.get('forma_pagamento')
            parcela = request.POST.get('parcela', '1')
            numdoc = request.POST.get('numdoc')
            rateio_obj = _regra_rateio_from_post(request, empresa_id)

            # Buscar fornecedor
            fornecedor = Fornecedor.objects.get(id=fornecedor_id, empresa_id=empresa_id)

            # Buscar categoria
            categoria = None
            if categoria_id:
                categoria = Categoria.objects.get(id=categoria_id, empresa_id=empresa_id)

            # Buscar cobrança
            forma_pagamento = None
            if forma_pagamento_id:
                forma_pagamento = Cobranca.objects.get(id=forma_pagamento_id)

            # Cobrança padrão (fallback) (primeira disponível)
            cobranca = Cobranca.objects.first()
            if not cobranca:
                # Criar uma cobrança padrão se não existir
                cobranca = Cobranca.objects.create(descricao='COBRANCA_PADRAO', tpag='00')

            # Buscar uma conta bancária padrão (primeira ativa da empresa)
            conta_banco = ContaBancaria.objects.filter(empresa_id=empresa_id, status='A').first()

            # Criar conta a pagar
            conta = ContasaPagar.objects.create(
                fornecedor=fornecedor,
                descricao=descricao,
                valorDoc=valor,
                dtEmissao=data_emissao,
                dtvenc=data_vencimento,
                categoria=categoria,
                cobranca=forma_pagamento or cobranca,
                conta_banco=conta_banco,
                parcela=parcela,
                numdoc=numdoc or '',
                status='pendente',
                empresa_id=empresa_id,
                rateio=rateio_obj,
                obs='',
                nossonumero='',
                nsu='',
            )

            messages.success(request, 'Conta a pagar criada com sucesso!')
            return redirect('contasapagar:listaAPagar')

        except Exception as e:
            messages.error(request, f'Erro ao criar conta: {str(e)}')
            return redirect('contasapagar:cadastrar')

    # GET: mostrar formulário
    fornecedores = Fornecedor.objects.filter(empresa_id=empresa_id)
    categorias = Categoria.objects.filter(empresa_id=empresa_id)
    formas_pagamento = Cobranca.objects.all()
    hoje = timezone.now().date()

    context = {
        'fornecedores': fornecedores,
        'categorias': categorias,
        'formas_pagamento': formas_pagamento,
        'hoje': hoje,
        'regras_rateio': RegraRateio.objects.filter(empresa_id=empresa_id).order_by('nomedaregra'),
    }
    return render(request, 'contasapagar/cadastrar.html', context)


@login_required
def baixar_conta_a_pagar(request, pk):
    """Baixar uma conta a pagar"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    conta = get_object_or_404(ContasaPagar, pk=pk, empresa_id=empresa_id)

    if request.method == 'POST':
        try:
            # Obter dados do formulário
            data_pagamento = request.POST.get('data_pagamento')
            valor_pago_str = request.POST.get('valor_pago')
            desconto_str = request.POST.get('desconto', '0')
            juros_str = request.POST.get('juros', '0')
            conta_banco_id = request.POST.get('conta_banco')
            lancamentos_conciliacao = request.POST.getlist('lancamentos_conciliacao')

            # Converter valores (Decimal — evita Decimal + float no modelo)
            if valor_pago_str and str(valor_pago_str).strip():
                valor_pago = _parse_decimal_br(valor_pago_str)
                if valor_pago is None:
                    valor_pago = conta.get_valor_total_com_ajustes()
            else:
                valor_pago = conta.get_valor_total_com_ajustes()
            desconto = _parse_decimal_br(desconto_str, Decimal('0')) or Decimal('0')
            juros = _parse_decimal_br(juros_str, Decimal('0')) or Decimal('0')

            # Buscar conta bancária
            conta_banco = None
            if conta_banco_id:
                conta_banco = ContaBancaria.objects.get(id=conta_banco_id, empresa_id=empresa_id)

            # Atualizar conta a pagar
            conta.dtPag = data_pagamento
            conta.valorPago = valor_pago
            conta.desconto = desconto
            conta.juros = juros
            conta.status = 'pago'
            conta.conta_banco = conta_banco
            conta.rateio = _regra_rateio_from_post(request, empresa_id)
            conta.save()

            # Criar movimento no extrato
            if conta_banco:
                from extrato.models import ExtratoMovimento, Lancamento, Conciliacao

                # Se houver lançamentos para conciliar, criar conciliação
                if lancamentos_conciliacao and conta_banco.tipo == 'CONTA_CORRENTE':
                    # Criar grupo de conciliação
                    conciliacao = Conciliacao.objects.create(
                        criado_por=request.user if request.user.is_authenticated else None
                    )

                    # Vincular lançamentos à conciliação
                    for lancamento_id in lancamentos_conciliacao:
                        lancamento = Lancamento.objects.get(id=lancamento_id, empresa_id=empresa_id)
                        lancamento.conciliado = True
                        lancamento.idconciliacao = conciliacao
                        lancamento.save()

                    # Criar movimento vinculado à conciliação
                    movimento = ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=data_pagamento,
                        descricao=f'Pagamento - {conta.descricao}',
                        valor=valor_pago,
                        situacao='pago',
                        conta_banco=conta_banco,
                        conta_pagar=conta
                    )

                    # Vincular movimento aos lançamentos conciliados
                    for lancamento_id in lancamentos_conciliacao:
                        lancamento = Lancamento.objects.get(id=lancamento_id, empresa_id=empresa_id)
                        movimento.lancamento = lancamento
                        movimento.save()
                        break  # Por enquanto, vincular apenas ao primeiro lançamento
                else:
                    # Criar movimento normal
                    ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=data_pagamento,
                        descricao=f'Pagamento - {conta.descricao}',
                        valor=valor_pago,
                        situacao='pago',
                        conta_banco=conta_banco,
                        conta_pagar=conta
                    )

            messages.success(request, f'Conta a pagar "{conta.descricao}" baixada com sucesso!')
            return redirect('contasapagar:listaAPagar')

        except Exception as e:
            messages.error(request, f'Erro ao baixar conta: {str(e)}')

    # GET: mostrar formulário de baixa
    contas_bancarias = ContaBancaria.objects.filter(empresa_id=empresa_id, status='A')

    context = {
        'conta': conta,
        'contas_bancarias': contas_bancarias,
        'regras_rateio': RegraRateio.objects.filter(empresa_id=empresa_id).order_by('nomedaregra'),
    }

    return render(request, 'contasapagar/baixar.html', context)


@login_required
def editar_conta_a_pagar(request, pk):
    """Editar uma conta a pagar"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    conta = get_object_or_404(ContasaPagar, pk=pk, empresa_id=empresa_id)

    if request.method == 'POST':
        try:
            # Obter dados do formulário
            fornecedor_id = request.POST.get('fornecedor')
            descricao = request.POST.get('descricao')
            valor_str = request.POST.get('valor')
            # Convert Brazilian decimal format (comma) to Python decimal format (dot)
            if valor_str:
                valor = float(valor_str.replace(',', '.'))
            else:
                valor = 0
            data_emissao = request.POST.get('data_emissao')
            data_vencimento = request.POST.get('data_vencimento')
            categoria_id = request.POST.get('categoria')
            forma_pagamento_id = request.POST.get('forma_pagamento')
            parcela = request.POST.get('parcela', '1')
            numdoc = request.POST.get('numdoc')
            rateio_obj = _regra_rateio_from_post(request, empresa_id)

            # Buscar fornecedor
            fornecedor = Fornecedor.objects.get(id=fornecedor_id, empresa_id=empresa_id)

            # Buscar categoria
            categoria = None
            if categoria_id:
                categoria = Categoria.objects.get(id=categoria_id, empresa_id=empresa_id)

            # Buscar cobrança
            forma_pagamento = None
            if forma_pagamento_id:
                forma_pagamento = Cobranca.objects.get(id=forma_pagamento_id)

            # Atualizar conta a pagar
            conta.fornecedor = fornecedor
            conta.descricao = descricao
            conta.valorDoc = valor
            conta.dtEmissao = data_emissao
            conta.dtvenc = data_vencimento
            conta.categoria = categoria
            conta.cobranca = forma_pagamento
            conta.parcela = parcela
            conta.numdoc = numdoc
            conta.rateio = rateio_obj
            conta.save()

            messages.success(request, 'Conta a pagar atualizada com sucesso!')
            return redirect('contasapagar:listaAPagar')

        except Exception as e:
            messages.error(request, f'Erro ao atualizar conta: {str(e)}')

    # GET: mostrar formulário preenchido
    fornecedores = Fornecedor.objects.filter(empresa_id=empresa_id)
    categorias = Categoria.objects.filter(empresa_id=empresa_id)
    formas_pagamento = Cobranca.objects.all()

    context = {
        'conta': conta,
        'fornecedores': fornecedores,
        'categorias': categorias,
        'formas_pagamento': formas_pagamento,
        'regras_rateio': RegraRateio.objects.filter(empresa_id=empresa_id).order_by('nomedaregra'),
    }

    return render(request, 'contasapagar/editar.html', context)


@login_required
@require_POST
def excluir_conta_a_pagar(request, pk):
    """Exclui uma conta a pagar"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    conta = get_object_or_404(ContasaPagar, pk=pk, empresa_id=empresa_id)

    # Verificar se a conta pode ser excluída (não está paga)
    if conta.status == 'pago':
        messages.error(request, 'Não é possível excluir uma conta já paga.')
        return redirect('contasapagar:listaAPagar')

    try:
        # Verificar se há movimentos relacionados no extrato
        from extrato.models import ExtratoMovimento
        movimentos_relacionados = ExtratoMovimento.objects.filter(conta_pagar=conta)

        if movimentos_relacionados.exists():
            messages.error(request, 'Não é possível excluir uma conta que possui movimentos conciliados no extrato.')
            return redirect('contasapagar:listaAPagar')

        # Excluir a conta
        conta.delete()
        messages.success(request, f'Conta a pagar "{conta.descricao}" excluída com sucesso.')

    except Exception as e:
        messages.error(request, f'Erro ao excluir conta: {str(e)}')

    return redirect('contasapagar:listaAPagar')

@login_required
def buscar_lancamentos_conciliacao(request, conta_banco_id):
    """Busca lançamentos disponíveis para conciliação (valores negativos)"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'success': False, 'error': 'Empresa não encontrada na sessão.'}, status=400)

    try:
        from extrato.models import Lancamento, ContaBancaria

        # Verificar se a conta bancária pertence à empresa
        conta_banco = ContaBancaria.objects.get(id=conta_banco_id, empresa_id=empresa_id)

        # DEBUG: Verificar lançamentos disponíveis antes do filtro de valor
        lancamentos_sem_filtro = Lancamento.objects.filter(
            empresa_id=empresa_id,
            conta=conta_banco,
            conciliado=False
        )
        print(f"DEBUG buscar_lancamentos_conciliacao: Total lançamentos não conciliados: {lancamentos_sem_filtro.count()}")

        # Verificar distribuição de valores
        valores = list(lancamentos_sem_filtro.values_list('valor', flat=True))
        print(f"DEBUG buscar_lancamentos_conciliacao: Valores encontrados: {valores}")

        # Buscar lançamentos não conciliados com valor negativo (débitos)
        lancamentos = Lancamento.objects.filter(
            empresa_id=empresa_id,
            conta=conta_banco,
            conciliado=False,
            valor__lt=0  # Apenas valores negativos (débitos)
        ).order_by('-data')[:50]  # Limitar a 50 lançamentos mais recentes

        print(f"DEBUG buscar_lancamentos_conciliacao: Lançamentos com valor < 0: {lancamentos.count()}")

        # Formatar dados para o frontend
        lancamentos_data = []
        for lancamento in lancamentos:
            lancamentos_data.append({
                'id': lancamento.id,
                'data': lancamento.data.strftime('%d/%m/%Y'),
                'historico': lancamento.historico,
                'valor': float(lancamento.valor),
                'documento': lancamento.documento or '',
            })

        return JsonResponse({
            'success': True,
            'lancamentos': lancamentos_data
        })

    except ContaBancaria.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Conta bancária não encontrada.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Erro interno: {str(e)}'}, status=500)


@login_required
@require_POST
def baixar_contas_selecionadas(request):
    """Baixar múltiplas contas a pagar selecionadas com conciliação automática"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    ids = request.POST.getlist("contas")
    if not ids:
        messages.warning(request, 'Nenhuma conta selecionada para baixar.')
        return redirect('contasapagar:listaAPagar')

    try:
        with transaction.atomic():
            # Buscar as contas a pagar selecionadas
            contas = ContasaPagar.objects.filter(id__in=ids, empresa_id=empresa_id, status='pendente')
            print(f"DEBUG: Contas a pagar para baixar: {[conta.id for conta in contas]}")
            contas_baixadas = 0
            contas_nao_conciliadas = []

            for conta in contas:
                # Tentar conciliar automaticamente
                conciliado = conciliar_conta_automaticamente(conta, empresa_id, request.user)

                if conciliado:
                    contas_baixadas += 1
                else:
                    contas_nao_conciliadas.append(conta.descricao)

            if contas_baixadas > 0:
                messages.success(request, f'{contas_baixadas} conta(s) baixada(s) com sucesso.')

            if contas_nao_conciliadas:
                messages.warning(request, f'Contas não conciliadas automaticamente: {", ".join(contas_nao_conciliadas)}. Baixe manualmente.')

            return redirect('contasapagar:listaAPagar')

    except Exception as e:
        messages.error(request, f'Erro ao baixar contas: {str(e)}')
        return redirect('contasapagar:listaAPagar')


def conciliar_conta_automaticamente(conta, empresa_id, user):
    """Tenta conciliar uma conta automaticamente com o extrato bancário"""
    from extrato.models import Lancamento, ContaBancaria, ExtratoMovimento, Conciliacao
    from datetime import timedelta

    print(f"DEBUG: Iniciando conciliação automática para conta {conta.id} - {conta.descricao}")

    # Verificar se o banco é Sicoob
    print(f"DEBUG: Conta {conta.id} - Verificando banco...")
    print(f"DEBUG: Conta {conta.id} - conta.conta_banco: {conta.conta_banco}")
    if conta.conta_banco:
        print(f"DEBUG: Conta {conta.id} - conta.conta_banco.banco: {conta.conta_banco.banco}")
        if conta.conta_banco.banco:
            nome_banco = conta.conta_banco.banco.nome
            nome_banco_lower = nome_banco.lower()
            print(f"DEBUG: Conta {conta.id} - Nome do banco: '{nome_banco}' (repr: {repr(nome_banco)})")
            print(f"DEBUG: Conta {conta.id} - Nome do banco lower: '{nome_banco_lower}' (repr: {repr(nome_banco_lower)})")
            print(f"DEBUG: Conta {conta.id} - Comparação: '{nome_banco_lower}' != 'sicoob' -> {nome_banco_lower != 'sicoob'}")

    if not conta.conta_banco or conta.conta_banco.banco.nome.lower() != 'sicoob':
        print(f"DEBUG: Conta {conta.id} - Banco não é Sicoob: {conta.conta_banco.banco.nome if conta.conta_banco and conta.conta_banco.banco else 'Nenhum banco'}")
        return False

    print(f"DEBUG: Conta {conta.id} - Banco Sicoob confirmado")

    # CPF/CNPJ: campo na conta (pode ser null) ou documento do fornecedor (campo cnpj = CPF ou CNPJ)
    from fornecedor.cnpj_utils import limpar_cnpj as _limpar_doc_fornecedor

    doc_digits = "".join(filter(str.isdigit, (conta.cpf_cnpj or "")))
    if len(doc_digits) < 4 and conta.fornecedor_id:
        doc_digits = _limpar_doc_fornecedor(conta.fornecedor.cnpj or "")
    cpf_cnpj_fornecedor = doc_digits if len(doc_digits) >= 4 else None
    if not cpf_cnpj_fornecedor:
        print(f"DEBUG: Conta {conta.id} - Fornecedor sem CPF/CNPJ: {conta.fornecedor.razao}")
        return False

    print(f"DEBUG: Conta {conta.id} - CPF/CNPJ fornecedor: {cpf_cnpj_fornecedor}")

    # Formatar CPF/CNPJ conforme especificado: ***.317.642-**
    cpf_formatado = formatar_cpf_cnpj_sicoob(cpf_cnpj_fornecedor)
    if not cpf_formatado:
        print(f"DEBUG: Conta {conta.id} - Falha na formatação do CPF/CNPJ")
        return False

    print(f"DEBUG: Conta {conta.id} - CPF/CNPJ formatado: {cpf_formatado}")

    # Definir período de busca: 15 dias antes e 30 dias depois da data de vencimento
    if not conta.dtvenc:
        print(f"DEBUG: Conta {conta.id} - Sem data de vencimento")
        return False
    data_inicio = conta.dtvenc - timedelta(days=15)
    data_fim = conta.dtvenc + timedelta(days=30)
    print(f"DEBUG: Conta {conta.id} - Período de busca: {data_inicio} a {data_fim}")

    # Buscar lançamentos não conciliados com valor negativo (débitos) no período
    lancamentos = Lancamento.objects.filter(
        empresa_id=empresa_id,
        conta=conta.conta_banco,
        conciliado=False,
        valor__lt = 0,  # Débitos
        data__gte=data_inicio,
        data__lte=data_fim,
        historico__icontains=cpf_formatado  # Verificar se contém o CPF formatado no histórico
    ).order_by('data')

    print(f"DEBUG: Conta {conta.id} - Lançamentos encontrados: {lancamentos.count()}")

    # Procurar lançamento com valor compatível
    valor_conta = conta.get_valor_total_com_ajustes()
    valor_conta_negativo = valor_conta * -1  # Tornar negativo para comparar com lançamentos de débito
    print(f"DEBUG: Conta {conta.id} - Valor conta: {valor_conta}, Valor negativo para comparação: {valor_conta_negativo}")

    for lancamento in lancamentos:
        valor_lancamento_abs = abs(lancamento.valor)
        print(f"DEBUG: Conta {conta.id} - Verificando lançamento {lancamento.id}: data={lancamento.data}, valor={lancamento.valor}, abs={valor_lancamento_abs}, historico='{lancamento.historico}'")
        # Comparar valores com tolerância de 0.01
        if abs(valor_lancamento_abs - valor_conta) <= 0.01:
            print(f"DEBUG: Conta {conta.id} - CORRESPONDÊNCIA ENCONTRADA! Lançamento {lancamento.id}")

            # Encontrou correspondência - conciliar
            conciliacao = Conciliacao.objects.create(
                criado_por=user if user.is_authenticated else None
            )

            # Marcar lançamento como conciliado
            lancamento.conciliado = True
            lancamento.idconciliacao = conciliacao
            lancamento.save()

            # Criar movimento no extrato
            movimento = ExtratoMovimento.objects.create(
                empresa_id=empresa_id,
                data_baixa=lancamento.data,
                descricao=f'Pagamento - {conta.descricao}',
                valor=valor_conta_negativo,
                situacao='pago',
                conta_banco=conta.conta_banco,
                conta_pagar=conta,
                lancamento=lancamento
            )

            # Atualizar conta a pagar
            conta.dtPag = lancamento.data
            conta.valorPago = valor_conta
            conta.status = 'pago'
            conta.save()

            print(f"DEBUG: Conta {conta.id} - CONCILIAÇÃO REALIZADA COM SUCESSO!")
            return True

    print(f"DEBUG: Conta {conta.id} - Nenhuma correspondência encontrada")
    return False


@login_required
@require_POST
def desconciliar_contas_pagar(request):
    """Desconciliar contas a pagar selecionadas"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    ids = request.POST.getlist("contas")
    if not ids:
        messages.warning(request, 'Nenhuma conta selecionada para desconciliar.')
        return redirect('contasapagar:listaAPagar')

    try:
        with transaction.atomic():
            # Buscar as contas a pagar selecionadas
            contas = ContasaPagar.objects.filter(id__in=ids, empresa_id=empresa_id)

            # Buscar movimentos do extrato relacionados
            from extrato.models import ExtratoMovimento
            movimentos = ExtratoMovimento.objects.filter(conta_pagar__in=contas)

            # Coletar contas a receber, baixas e relatórios relacionados
            contas_a_receber = []
            baixas_a_deletar = []
            relatorios_a_reverter = []

            for movimento in movimentos:
                if movimento.conta_receber:
                    contas_a_receber.append(movimento.conta_receber)
                if hasattr(movimento, 'baixa_receber') and movimento.baixa_receber:
                    baixas_a_deletar.append(movimento.baixa_receber)

                # Buscar relatórios relacionados ao movimento (através da conta_receber)
                if movimento.conta_receber:
                    from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao
                    relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        conta_a_receber=movimento.conta_receber,
                        empresa_id=empresa_id,
                        conciliado=True
                    )
                    relatorios_a_reverter.extend(relatorios)

            # Buscar relatórios vinculados via identificacao_extrato
            from extrato.models import Lancamento
            for conta in contas:
                # Buscar lançamentos relacionados à conta
                lancamentos_relacionados = Lancamento.objects.filter(
                    empresa_id=empresa_id,
                    extrato_movimentos__conta_pagar=conta
                ).distinct()

                for lancamento in lancamentos_relacionados:
                    if lancamento.fitid:
                        from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao
                        relatorios_por_fitid = RelatorioRecebiveisMaquinaCartao.objects.filter(
                            identificacao_extrato__icontains=str(lancamento.fitid),
                            empresa_id=empresa_id,
                            conciliado=True
                        )
                        relatorios_a_reverter.extend(relatorios_por_fitid)

                        # Coletar contas a receber vinculadas a estes relatórios
                        for relatorio in relatorios_por_fitid:
                            if relatorio.conta_a_receber and relatorio.conta_a_receber not in contas_a_receber:
                                contas_a_receber.append(relatorio.conta_a_receber)

            # Deletar as baixas relacionadas
            from contasareceber.models import BaixaContaAReceber
            if baixas_a_deletar:
                BaixaContaAReceber.objects.filter(id__in=[b.id for b in baixas_a_deletar]).delete()

            # Reverter relatórios para não conciliados
            for relatorio in relatorios_a_reverter:
                relatorio.conciliado = False
                relatorio.identificacao_extrato = ''
                relatorio.save()

            # Reverter contas a receber para status cartao ou excluir se foram criadas automaticamente
            contas_para_deletar = []
            contas_para_reverter = []

            for conta in contas_a_receber:
                # Verificar se a conta foi criada automaticamente (sem nota fiscal e doc começa com 'Relatorio ')
                if conta.nota is None and conta.doc and conta.doc.startswith('Relatorio '):
                    contas_para_deletar.append(conta)
                else:
                    contas_para_reverter.append(conta)

            # Excluir contas criadas automaticamente
            if contas_para_deletar:
                for conta in contas_para_deletar:
                    # Remover associação dos relatórios
                    from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao
                    relatorios_associados = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        conta_a_receber=conta,
                        empresa_id=empresa_id
                    )
                    for relatorio in relatorios_associados:
                        relatorio.conta_a_receber = None
                        relatorio.save()

                    # Excluir a conta
                    conta.delete()

            # Reverter contas normais para status cartao ou pendente
            for conta in contas_para_reverter:
                # Verificar se a conta tem relatório de recebíveis (cartão)
                from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao
                relatorio_cartao = RelatorioRecebiveisMaquinaCartao.objects.filter(
                    conta_a_receber=conta,
                    empresa_id=empresa_id
                ).exists()

                if relatorio_cartao:
                    # Valor vindo do relatório de recebíveis (cartão)
                    conta.status = 'cartao'
                else:
                    # Valor vindo de PIX ou TED - colocar como pendente
                    conta.status = 'pendente'

                # Limpar campos de recebimento
                conta.data_recebimento = None
                conta.valor_recebido = 0
                conta.desconto = 0
                conta.juros = 0
                conta.tarifas = 0
                conta.save()

                # Atualizar status de conciliação da nota
                if conta.nota:
                    # Import necessário
                    from contasareceber.models import ContaAReceber

                    # Verificar se há outras contas da mesma nota que ainda estão pagas
                    outras_contas_pagas = ContaAReceber.objects.filter(
                        nota=conta.nota,
                        empresa_id=empresa_id,
                        status='pago'
                    ).exclude(id=conta.id).exists()

                    if outras_contas_pagas:
                        # Se há outras contas pagas, manter como parcialmente conciliado
                        conta.nota.status_conciliacao = 'parcialmente_conciliado'
                    else:
                        # Se não há outras contas pagas, voltar para não conciliado
                        conta.nota.status_conciliacao = 'nao_conciliado'
                    conta.nota.save()

            # Deletar os movimentos do extrato
            movimentos.delete()

            # Reverter contas a pagar para status pendente
            for conta in contas:
                conta.status = 'pendente'
                conta.dtPag = None
                conta.valorPago = 0
                conta.desconto = 0
                conta.juros = 0
                conta.save()

            # Desconciliar lançamentos relacionados
            lancamentos_para_desconciliar = Lancamento.objects.filter(
                empresa_id=empresa_id,
                extrato_movimentos__conta_pagar__in=contas
            ).distinct()

            lancamentos_para_desconciliar.update(conciliado=False)

            messages.success(request, f"{len(ids)} conta(s) a pagar desconciliada(s) com sucesso.")
            return redirect('contasapagar:listaAPagar')

    except Exception as e:
        messages.error(request, f'Erro ao desconciliar contas: {str(e)}')
        return redirect('contasapagar:listaAPagar')


@login_required
def aplicar_categoria(request):
    """Aplicar categoria a múltiplas contas a pagar selecionadas"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    if request.method != 'POST':
        return redirect('contasapagar:listaAPagar')

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada.')
        return redirect('contasapagar:listaAPagar')

    # Obter dados do formulário
    contas_ids = request.POST.getlist('contas_ids')
    categoria_id = request.POST.get('categoria_id')

    if not contas_ids:
        messages.error(request, 'Nenhuma conta selecionada.')
        return redirect('contasapagar:listaAPagar')

    if not categoria_id:
        messages.error(request, 'Categoria não selecionada.')
        return redirect('contasapagar:listaAPagar')

    try:
        # Buscar categoria
        categoria = Categoria.objects.get(id=categoria_id, empresa_id=empresa_id)
    except Categoria.DoesNotExist:
        messages.error(request, 'Categoria não encontrada ou não pertence à empresa.')
        return redirect('contasapagar:listaAPagar')

    # Buscar contas selecionadas
    contas = ContasaPagar.objects.filter(id__in=contas_ids, empresa_id=empresa_id)

    aplicadas = 0

    for conta in contas:
        try:
            # Aplicar categoria à conta
            conta.categoria = categoria
            conta.save()
            aplicadas += 1

        except Exception as e:
            print(f"Erro ao aplicar categoria à conta {conta.id}: {str(e)}")
            continue

    if aplicadas > 0:
        messages.success(request, f'Categoria "{categoria.nome}" aplicada a {aplicadas} conta(s) com sucesso.')
    else:
        messages.warning(request, 'Nenhuma conta foi atualizada.')

    return redirect('contasapagar:listaAPagar')


@login_required
def buscar_categorias(request):
    """Busca categorias para autocomplete"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'error': 'Empresa não encontrada na sessão.'}, status=400)

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({'error': 'Empresa não encontrada.'}, status=404)

    termo = request.GET.get('q', '').strip()
    if len(termo) < 4:
        return JsonResponse({'categorias': []})

    # Buscar categorias que contenham o termo no nome ou classificação
    categorias = Categoria.objects.filter(
        empresa=empresa
    ).filter(
        Q(nome__icontains=termo) | Q(classificacao__icontains=termo)
    ).order_by('tipo', 'nome')[:20]  # Limitar a 20 resultados

    # Preparar dados para resposta
    categorias_data = []
    for categoria in categorias:
        tipo_display = {
            'R': 'Receita',
            'D': 'Despesa',
            'I': 'Investimento',
            'L': 'Distribuição de Lucro'
        }.get(categoria.tipo, categoria.tipo)

        categorias_data.append({
            'id': categoria.id,
            'nome': categoria.nome,
            'classificacao': categoria.classificacao,
            'nome_completo': f"{categoria.classificacao} {categoria.nome}",
            'tipo': categoria.tipo,
            'tipo_display': tipo_display,
            'grupo': categoria.grupo
        })

    return JsonResponse({'categorias': categorias_data})


@login_required
def importar_pdf_contas_pagar(request):
    """View para importar contas a pagar de arquivo PDF"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('contasapagar:listaAPagar')

    if request.method == 'POST':
        try:
            # Verificar se foi enviado um arquivo
            if 'pdf_file' not in request.FILES:
                messages.error(request, 'Nenhum arquivo PDF foi selecionado.')
                return redirect('contasapagar:importar_pdf')

            pdf_file = request.FILES['pdf_file']

            # Debug: verificar se o arquivo foi recebido
            print(f"DEBUG: Arquivo recebido: {pdf_file.name}, tamanho: {pdf_file.size} bytes")

            # Validar tipo do arquivo
            if not pdf_file.name.lower().endswith('.pdf'):
                messages.error(request, 'O arquivo deve ser um PDF.')
                return redirect('contasapagar:importar_pdf')

            # Buscar empresa
            from empresa.models import Empresa
            empresa = Empresa.objects.get(id=empresa_id)

            # Processar PDF e criar contas a pagar
            contas_criadas, erro = processar_pdf_contas_pagar(pdf_file, empresa)

            if erro:
                messages.error(
                    request,
                    "Importação não realizada. " + erro,
                )
                return redirect("contasapagar:importar_pdf")
            if contas_criadas:
                messages.success(
                    request,
                    f"{len(contas_criadas)} conta(s) a pagar importada(s) com sucesso do PDF!",
                )
                return redirect("contasapagar:listaAPagar")
            messages.warning(
                request,
                "Importação não concluída: nenhuma conta a pagar foi gerada a partir deste PDF. "
                "Confira se o arquivo é um comprovante válido da Receita Federal e se o CNPJ confere com a empresa.",
            )
            return redirect("contasapagar:importar_pdf")

        except Exception as e:
            messages.error(request, f'Erro ao processar PDF: {str(e)}')
            return redirect('contasapagar:importar_pdf')

    # GET: mostrar formulário de upload
    return render(request, 'contasapagar/importar_pdf.html')


@login_required
def importar_relatorio_liquidos(request):
    """Upload do PDF Relação Geral dos Líquidos / relatório de líquidos da folha."""
    empresa_id = request.session.get("empresa_id")
    if not empresa_id:
        messages.error(request, "Empresa não encontrada na sessão.")
        return redirect("contasapagar:listaAPagar")

    if request.method == "POST":
        try:
            if "pdf_file" not in request.FILES:
                messages.error(request, "Nenhum arquivo PDF foi selecionado.")
                return redirect("contasapagar:importar_relatorio_liquidos")

            pdf_file = request.FILES["pdf_file"]
            if not pdf_file.name.lower().endswith(".pdf"):
                messages.error(request, "O arquivo deve ser um PDF.")
                return redirect("contasapagar:importar_relatorio_liquidos")

            from empresa.models import Empresa

            empresa = Empresa.objects.get(id=empresa_id)
            contas_criadas, erro = processar_relatorio_liquidos_pdf(pdf_file, empresa)

            if erro:
                messages.error(
                    request,
                    "Importação não realizada. " + erro,
                )
                return redirect("contasapagar:importar_relatorio_liquidos")
            if contas_criadas:
                messages.success(
                    request,
                    f"{len(contas_criadas)} conta(s) a pagar gerada(s) a partir do Relatório de Líquidos.",
                )
                return redirect("contasapagar:listaAPagar")
            messages.warning(
                request,
                "Importação não concluída: nenhuma conta nova foi gerada. "
                "Verifique categorias (Encargos/Salário), cobrança PIX, CNPJ do PDF x empresa na sessão, "
                "PDF com texto selecionável ou GEMINI_API_KEY, e se os lançamentos já existem.",
            )
            return redirect("contasapagar:importar_relatorio_liquidos")

        except Exception as e:
            messages.error(request, f"Erro ao importar: {str(e)}")
            return redirect("contasapagar:importar_relatorio_liquidos")

    return render(request, "contasapagar/importar_relatorio_liquidos.html")