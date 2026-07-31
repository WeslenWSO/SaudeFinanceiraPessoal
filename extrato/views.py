import hashlib
import logging
import uuid
from decimal import Decimal
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db import transaction
from django.db.models import Max, Q
from django.http import JsonResponse
from datetime import datetime, timedelta, date
from calendar import monthrange
from dateutil.relativedelta import relativedelta

from .models import Lancamento, Conciliacao, ExtratoArquivo, ContaBancaria, ExtratoMovimento
from .forms import LancamentoForm, UploadOFXForm, UploadPDFForm, TransferenciaForm, ContaBancariaForm
from .services.ofx_importer import import_ofx
from .services.pdf_importer import import_pdf
from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao
from categoria.models import Categoria
from cobranca.models import Cobranca  # antes: formapgto.models.FormaPgto (removido)
from fornecedor.models import Fornecedor
from contasapagar.models import ContasaPagar

logger = logging.getLogger(__name__)


def extrair_cpf_mascarado(historico):
    """
    Extrai CPF mascarado do histórico do lançamento.
    Para SICOOB: ***.XXX.XXX-**
    """
    import re
    # Padrão para CPF mascarado SICOOB: ***.XXX.XXX-**
    padrao = r'\*\*\*\.(\d{3})\.(\d{3})\-\*\*'
    match = re.search(padrao, historico)
    if match:
        return f"***.{match.group(1)}.{match.group(2)}-**"
    return None


def limpar_cpf(cpf):
    """
    Remove formatação do CPF, deixando apenas dígitos
    """
    return ''.join(filter(str.isdigit, cpf))


def mascarar_cpf_sicoob(cpf):
    """
    Mascara CPF no formato SICOOB: ***.XXX.XXX-**
    """
    cpf_limpo = limpar_cpf(cpf)
    if len(cpf_limpo) == 11:
        return f"***.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-**"
    return cpf


def extrair_nome_pix(historico):
    """
    Extrai o nome do recebedor de uma transação PIX do histórico.
    Exemplo: "PIX RECEBIDO - OUTRA IF - Recebimento Pix Charles Roberto Oliveira Dos Santos ***.406.302-**"
    Retorna: "Charles Roberto Oliveira Dos Santos"
    """
    import re
    # Padrão para capturar o nome após "Recebimento Pix " e antes do CPF mascarado
    padrao = r'Recebimento Pix (.+?)\s+\*\*\*'
    match = re.search(padrao, historico)
    if match:
        return match.group(1).strip()
    return None


def aplicar_filtros_lancamento_list(queryset, request):
    """
    Aplica os mesmos filtros usados no LancamentoListView
    Retorna o queryset filtrado
    """
    empresa_id = request.session.get('empresa_id')
    contas_ids = request.GET.getlist("contas")  # Multiple accounts
    conta_id = request.GET.get("conta")  # Keep for backward compatibility
    conciliado = request.GET.get("conciliado")
    periodo = request.GET.get("periodo")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")
    valor_de = request.GET.get("valor_de")
    valor_ate = request.GET.get("valor_ate")
    historico = request.GET.get("historico")
    tipo_valor = request.GET.get("tipo_valor")  # Novo filtro: receita/despesa

    if empresa_id:
        queryset = queryset.filter(empresa_id=empresa_id)

    # Handle multiple accounts or single account
    if contas_ids:
        queryset = queryset.filter(conta_id__in=contas_ids)
    elif conta_id:
        queryset = queryset.filter(conta_id=conta_id)

    if conciliado in ["0","1"]:
        queryset = queryset.filter(conciliado=(conciliado == "1"))

    # Aplicar filtro de período
    if periodo:
        hoje = datetime.now().date()
        if periodo == "7d":
            data_inicio = hoje - timedelta(days=7)
        elif periodo == "30d":
            data_inicio = hoje - timedelta(days=30)
        elif periodo == "90d":
            data_inicio = hoje - timedelta(days=90)
        elif periodo == "6m":
            data_inicio = hoje - relativedelta(months=6)
        elif periodo == "12m":
            data_inicio = hoje - relativedelta(months=12)
        elif periodo == "custom":
            # Usar data_inicio e data_fim do GET
            pass
        else:
            # Período personalizado antigo
            try:
                data_inicio_str, data_fim_str = periodo.split(' to ')
                data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            except:
                pass

    # Aplicar filtros de data
    if data_inicio:
        try:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            queryset = queryset.filter(data__gte=data_inicio)
        except:
            pass
    if data_fim:
        try:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            queryset = queryset.filter(data__lte=data_fim)
        except:
            pass

    # Aplicar filtros de valor
    if valor_de:
        try:
            valor_de = Decimal(valor_de)
            queryset = queryset.filter(valor__gte=valor_de)
        except:
            pass
    if valor_ate:
        try:
            valor_ate = Decimal(valor_ate)
            queryset = queryset.filter(valor__lte=valor_ate)
        except:
            pass

    # Aplicar filtro de histórico
    if historico:
        queryset = queryset.filter(historico__icontains=historico)

    # Aplicar filtro de tipo de valor (receita/despesa)
    if tipo_valor == "receita":
        queryset = queryset.filter(valor__gt=0)
    elif tipo_valor == "despesa":
        queryset = queryset.filter(valor__lt=0)

    return queryset


def _map_saldo_progressivo_por_lancamento(empresa_id, conta_ids):
    """
    Saldo progressivo por lançamento, partindo do saldo inicial da conta.

    A partir da data inicial do saldo, o cálculo segue o extrato real:
    saldo = saldo_inicial + soma dos lançamentos (independente de status/conciliação).
    """
    saldo_por_lancamento = {}
    if not empresa_id or not conta_ids:
        return saldo_por_lancamento

    contas = (
        ContaBancaria.objects.filter(empresa_id=empresa_id, id__in=conta_ids)
        .only('id', 'saldo_inicial', 'data_inicial_saldo')
    )

    for conta in contas:
        movimentos = list(
            Lancamento.objects.filter(empresa_id=empresa_id, conta_id=conta.id)
            .order_by('data', 'criado_em', 'id')
            .only('id', 'data', 'valor')
        )
        saldo_inicial = conta.saldo_inicial or Decimal('0.00')
        data_base = conta.data_inicial_saldo

        if data_base:
            total_antes_base = sum(
                (mov.valor for mov in movimentos if mov.data and mov.data < data_base),
                Decimal('0.00'),
            )
            saldo_atual = saldo_inicial - total_antes_base
        else:
            saldo_atual = saldo_inicial

        for mov in movimentos:
            saldo_atual += mov.valor
            saldo_por_lancamento[mov.id] = saldo_atual

    return saldo_por_lancamento


class LancamentoListView(ListView):
    model = Lancamento
    template_name = 'extrato/lancamento_list.html'
    paginate_by = 50
    ordering = ["data", "criado_em"]  # Ordem crescente para calcular saldo corretamente

    def get_paginate_by(self, queryset):
        """
        Retorna o número de itens por página baseado no parâmetro GET 'paginate_by'
        """
        paginate_by = self.request.GET.get('paginate_by')
        if paginate_by and paginate_by.isdigit():
            return int(paginate_by)
        return self.paginate_by

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        contas_ids = self.request.GET.getlist("contas")  # Multiple accounts
        conta_id = self.request.GET.get("conta")  # Keep for backward compatibility
        conciliado = self.request.GET.get("conciliado")
        periodo = self.request.GET.get("periodo")
        data_inicio = self.request.GET.get("data_inicio")
        data_fim = self.request.GET.get("data_fim")
        valor_de = self.request.GET.get("valor_de")
        valor_ate = self.request.GET.get("valor_ate")
        historico = self.request.GET.get("historico")
        tipo_valor = self.request.GET.get("tipo_valor")  # Novo filtro: receita/despesa

        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        # Handle multiple accounts or single account
        if contas_ids:
            qs = qs.filter(conta_id__in=contas_ids)
        elif conta_id:
            qs = qs.filter(conta_id=conta_id)

        if conciliado in ["0","1"]:
            qs = qs.filter(conciliado=(conciliado == "1"))

        # Período padrão: último mês que teve lançamentos importados (OFX/PDF); senão mês passado
        if not data_inicio and not data_fim:
            hoje = datetime.now().date()
            primeiro_dia_mes_passado = date(hoje.year, hoje.month, 1) - relativedelta(months=1)
            ultimo_dia_mes_passado = date(hoje.year, hoje.month, 1) - timedelta(days=1)
            if empresa_id:
                qs_importados = Lancamento.objects.filter(empresa_id=empresa_id).filter(
                    Q(extrato_arquivo__isnull=False) | Q(origem__in=['OFX', 'PDF'])
                )
                ultima_data = qs_importados.aggregate(ultima=Max('data'))['ultima']
                if ultima_data:
                    primeiro_dia = date(ultima_data.year, ultima_data.month, 1)
                    ultimo_dia = date(ultima_data.year, ultima_data.month, monthrange(ultima_data.year, ultima_data.month)[1])
                    data_inicio = primeiro_dia
                    data_fim = ultimo_dia
                    self.data_inicio_padrao = primeiro_dia
                    self.data_fim_padrao = ultimo_dia
                else:
                    data_inicio = primeiro_dia_mes_passado
                    data_fim = ultimo_dia_mes_passado
                    self.data_inicio_padrao = primeiro_dia_mes_passado
                    self.data_fim_padrao = ultimo_dia_mes_passado
            else:
                data_inicio = primeiro_dia_mes_passado
                data_fim = ultimo_dia_mes_passado
                self.data_inicio_padrao = primeiro_dia_mes_passado
                self.data_fim_padrao = ultimo_dia_mes_passado

        # Aplicar filtro de período
        if periodo:
            hoje = datetime.now().date()


            try:
                    data_inicio_str, data_fim_str = periodo.split(' to ')
                    data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            except:
                    pass

        # Aplicar filtros de data
        if data_inicio:
            try:
                if isinstance(data_inicio, str):
                    data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
                qs = qs.filter(data__gte=data_inicio)
            except:
                pass
        if data_fim:
            try:
                if isinstance(data_fim, str):
                    data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=data_fim)
            except:
                pass

        # Aplicar filtros de valor
        if valor_de:
            try:
                valor_de = Decimal(valor_de)
                qs = qs.filter(valor__gte=valor_de)
            except:
                pass
        if valor_ate:
            try:
                valor_ate = Decimal(valor_ate)
                qs = qs.filter(valor__lte=valor_ate)
            except:
                pass

        # Aplicar filtro de histórico
        if historico:
            qs = qs.filter(historico__icontains=historico)

        # Aplicar filtro de tipo de valor (receita/despesa)
        if tipo_valor == "receita":
            qs = qs.filter(valor__gt=0)
        elif tipo_valor == "despesa":
            qs = qs.filter(valor__lt=0)

        # Armazenar o total antes de paginar
        self.total_lancamentos = qs.count()

        # Calcular saldo progressivo
        lancamentos = list(qs)

        # Soma de entradas (valores > 0) e retiradas (valores < 0) no mesmo período/filtros
        soma_entradas = Decimal('0.00')
        soma_retiradas = Decimal('0.00')
        for l in lancamentos:
            v = l.valor
            if v > 0:
                soma_entradas += v
            elif v < 0:
                soma_retiradas += v
        self.soma_entradas = soma_entradas
        self.soma_retiradas = soma_retiradas

        conta_ids = {l.conta_id for l in lancamentos if l.conta_id}
        saldos_mapeados = _map_saldo_progressivo_por_lancamento(empresa_id, conta_ids)
        for lancamento in lancamentos:
            if lancamento.id in saldos_mapeados:
                lancamento.saldo_calculado = saldos_mapeados[lancamento.id]
            else:
                lancamento.saldo_calculado = lancamento.valor

        return lancamentos

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Adicionar apenas a empresa logada para o filtro
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            from empresa.models import Empresa
            try:
                empresa_logada = Empresa.objects.get(id=empresa_id)
                context['empresas'] = [empresa_logada]  # Lista com apenas a empresa logada
            except Empresa.DoesNotExist:
                context['empresas'] = []

            # Adicionar contas bancárias da empresa logada
            from .models import ContaBancaria
            contas = ContaBancaria.objects.filter(
                empresa_id=empresa_id
            ).order_by('banco__nome')

            # Adicionar categorias para o modal de conciliação de despesa (apenas despesas)
            from categoria.models import Categoria
            context['categorias'] = Categoria.objects.filter(empresa_id=empresa_id).exclude(tipo='R').order_by('nome')

            # Adicionar formas de pagamento
            context['formas_pagamento'] = Cobranca.objects.all().order_by('descricao')

            # Adicionar fornecedores
            from fornecedor.models import Fornecedor
            context['fornecedores'] = Fornecedor.objects.filter(empresa_id=empresa_id).order_by('razao')

            # Calcular saldo atual por conta com base no saldo inicial + movimentos do extrato
            for conta in contas:
                ultimo_lancamento = Lancamento.objects.filter(
                    empresa_id=empresa_id,
                    conta=conta
                ).order_by('-data').first()

                if ultimo_lancamento:
                    lancamentos_conta = list(
                        Lancamento.objects.filter(
                            empresa_id=empresa_id,
                            conta=conta,
                        ).order_by('data', 'criado_em', 'id')
                    )

                    saldo_inicial = conta.saldo_inicial or Decimal('0.00')
                    data_base = conta.data_inicial_saldo
                    if data_base:
                        total_antes_base = sum(
                            (lanc.valor for lanc in lancamentos_conta if lanc.data and lanc.data < data_base),
                            Decimal('0.00'),
                        )
                        saldo_atual = saldo_inicial - total_antes_base
                    else:
                        saldo_atual = saldo_inicial

                    for lanc in lancamentos_conta:
                        saldo_atual += lanc.valor

                    conta.saldo_atual = saldo_atual
                    conta.ultimo_lancamento_data = ultimo_lancamento.data
                else:
                    conta.saldo_atual = conta.saldo_inicial or Decimal('0.00')
                    conta.ultimo_lancamento_data = None

            context['contas'] = contas
            context['contas_sicoob'] = list(
                contas.filter(
                    Q(banco__codigo__in=['756', '0756', '0306', '306']) | Q(banco__nome__icontains='sicoob')
                ).select_related('banco').distinct()
            )
        else:
            context['empresas'] = []
            context['contas'] = []
            context['contas_sicoob'] = []

        # Adicionar opções de período
        context['periodos'] = [
            {'value': '30d', 'label': 'Últimos 30 dias'},
            {'value': 'custom', 'label': 'Personalizado'},
        ]

        # Período selecionado
        periodo = self.request.GET.get('periodo', '')
        context['periodo_selecionado'] = periodo

        # Datas para período personalizado
        data_inicio_get = self.request.GET.get('data_inicio', '')
        data_fim_get = self.request.GET.get('data_fim', '')
        if not data_inicio_get and not data_fim_get:
            # Usar período padrão (mês passado) se não houver filtros GET
            # Verificar se as datas padrão foram definidas no get_queryset
            if hasattr(self, 'data_inicio_padrao') and hasattr(self, 'data_fim_padrao'):
                context['data_inicio'] = self.data_inicio_padrao.strftime('%Y-%m-%d')
                context['data_fim'] = self.data_fim_padrao.strftime('%Y-%m-%d')
            else:
                # Fallback para o cálculo direto
                hoje = datetime.now().date()
                primeiro_dia_mes_passado = date(hoje.year, hoje.month, 1) - relativedelta(months=1)
                ultimo_dia_mes_passado = date(hoje.year, hoje.month, 1) - timedelta(days=1)
                context['data_inicio'] = primeiro_dia_mes_passado.strftime('%Y-%m-%d')
                context['data_fim'] = ultimo_dia_mes_passado.strftime('%Y-%m-%d')
        else:
            context['data_inicio'] = data_inicio_get
            context['data_fim'] = data_fim_get

        # Total de lançamentos (não apenas da página)
        context['total_lancamentos'] = getattr(self, 'total_lancamentos', 0)

        se = getattr(self, 'soma_entradas', Decimal('0.00'))
        sr = getattr(self, 'soma_retiradas', Decimal('0.00'))
        context['soma_entradas'] = se
        context['soma_retiradas'] = sr
        # Soma algébrica dos negativos (≤ 0); para exibição como valor positivo “retirado”
        ra = abs(sr) if sr else Decimal('0.00')
        context['soma_retiradas_abs'] = ra
        # Liquido do período: entradas − retiradas (retiradas em valor positivo)
        context['total_movimentacao'] = se - ra

        # Contas selecionadas para o filtro
        context['contas_selecionadas'] = self.request.GET.getlist("contas")

        # Tipo de valor selecionado para o filtro
        context['tipo_valor_selecionado'] = self.request.GET.get('tipo_valor', '')

        # Verificar se há lançamentos não conciliados com valor > 0 no período filtrado
        contas_ids = self.request.GET.getlist("contas")  # Multiple accounts
        conta_id = self.request.GET.get("conta")  # Keep for backward compatibility
        conciliado = self.request.GET.get("conciliado")
        data_inicio = self.request.GET.get("data_inicio")
        data_fim = self.request.GET.get("data_fim")

        qs_nao_conciliados = Lancamento.objects.filter(empresa_id=empresa_id, conciliado=False, valor__gt=0)

        # Aplicar filtros de contas
        if contas_ids:
            qs_nao_conciliados = qs_nao_conciliados.filter(conta_id__in=contas_ids)
        elif conta_id:
            qs_nao_conciliados = qs_nao_conciliados.filter(conta_id=conta_id)

        # Aplicar filtro de período
        if periodo:
            hoje = datetime.now().date()
            if periodo == "7d":
                data_inicio = hoje - timedelta(days=7)
                data_fim = hoje
            elif periodo == "30d":
                data_inicio = hoje - timedelta(days=30)
                data_fim = hoje
            elif periodo == "90d":
                data_inicio = hoje - timedelta(days=90)
                data_fim = hoje
            elif periodo == "6m":
                data_inicio = hoje - relativedelta(months=6)
                data_fim = hoje
            elif periodo == "12m":
                data_inicio = hoje - relativedelta(months=12)
                data_fim = hoje
            elif periodo == "custom":
                # Usar data_inicio e data_fim do GET
                pass
            else:
                # Período personalizado antigo
                try:
                    data_inicio_str, data_fim_str = periodo.split(' to ')
                    data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                    data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
                except:
                    pass

        # Aplicar filtros de data
        if data_inicio:
            try:
                data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
                qs_nao_conciliados = qs_nao_conciliados.filter(data__gte=data_inicio)
            except:
                pass
        if data_fim:
            try:
                data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
                qs_nao_conciliados = qs_nao_conciliados.filter(data__lte=data_fim)
            except:
                pass

        # Verificar se há lançamentos não conciliados
        context['tem_lancamentos_nao_conciliados'] = qs_nao_conciliados.exists()

        # Informações sobre navegação por meses
        hoje = datetime.now().date()
        mes_atual_visualizacao = self.request.session.get('extrato_mes_atual', hoje.year * 12 + hoje.month)

        # Converter de volta para ano e mês
        ano_atual = mes_atual_visualizacao // 12
        mes_atual = mes_atual_visualizacao % 12
        if mes_atual == 0:
            ano_atual -= 1
            mes_atual = 12

        # Calcular limite (12 meses para trás)
        mes_limite = hoje.year * 12 + hoje.month - 12

        # Determinar o texto do período selecionado
        periodo_texto = ''
        if periodo in ["mes_atual", "mes_anterior"] or not periodo:
            import calendar
            nome_mes = calendar.month_name[mes_atual]
            periodo_texto = f"{nome_mes} {ano_atual}"

        # Determinar se pode navegar para trás
        pode_navegar_anterior = mes_atual_visualizacao > mes_limite

        context['periodo_texto'] = periodo_texto
        context['pode_navegar_anterior'] = pode_navegar_anterior

        return context

class LancamentoCreateView(CreateView):
    model = Lancamento
    form_class = LancamentoForm
    template_name = 'extrato/lancamento_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            kwargs['empresa_id'] = empresa_id
        return kwargs

    def get_success_url(self):
        return reverse("extrato:lancamento_list")


# View para ExtratoMovimento
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST


@login_required
@require_POST
def importar_extrato_sicoob(request):
    """POST: importa extrato da API Sicoob para a conta informada (mês/ano)."""
    empresa_id = request.session.get("empresa_id")
    if not empresa_id:
        messages.error(request, "Selecione uma empresa para continuar.")
        return redirect("empresa:lista")

    conta_id = request.POST.get("conta_id")
    mes_s = request.POST.get("mes")
    ano_s = request.POST.get("ano")
    dia_ini = request.POST.get("dia_inicial") or None
    dia_fim = request.POST.get("dia_final") or None

    if not conta_id or not mes_s or not ano_s:
        messages.error(request, "Informe conta, mês e ano.")
        return redirect("extrato:lancamento_list")

    try:
        mes = int(mes_s)
        ano = int(ano_s)
        if mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
            raise ValueError("período")
    except ValueError:
        messages.error(request, "Mês ou ano inválidos.")
        return redirect("extrato:lancamento_list")

    conta = get_object_or_404(
        ContaBancaria.objects.select_related("banco"),
        pk=int(conta_id),
        empresa_id=empresa_id,
        status="A",
    )
    cod = (conta.banco.codigo or "").strip().lstrip("0") or (conta.banco.codigo or "")
    nome_b = (conta.banco.nome or "").lower()
    if cod not in ("756", "306") and "sicoob" not in nome_b:
        messages.error(request, "A conta selecionada não é Sicoob.")
        return redirect("extrato:lancamento_list")

    d_ini = int(dia_ini) if dia_ini and str(dia_ini).isdigit() else None
    d_fim = int(dia_fim) if dia_fim and str(dia_fim).isdigit() else None

    logger.info(
        "importar_extrato_sicoob (view) | user=%s empresa_id=%s conta_id=%s mes=%s ano=%s dia_inicial=%s dia_final=%s",
        getattr(request.user, "pk", None),
        empresa_id,
        conta_id,
        mes,
        ano,
        d_ini,
        d_fim,
    )

    try:
        from .services.sicoob_import import importar_extrato_sicoob_para_conta

        criados, ignorados, msg = importar_extrato_sicoob_para_conta(
            conta, mes, ano, dia_inicial=d_ini, dia_final=d_fim
        )
        messages.success(request, msg)
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.exception("importar_extrato_sicoob")
        messages.error(request, f"Erro ao importar extrato Sicoob: {e}")

    return redirect("extrato:lancamento_list")


@method_decorator(login_required, name='dispatch')
class ExtratoMovimentoListView(ListView):
    model = ExtratoMovimento
    template_name = 'extrato/extrato_movimento_list.html'
    context_object_name = 'movimentos'
    paginate_by = 25

    def get_queryset(self):
        from contasareceber.models import ContaAReceber
        from contasapagar.models import ContasaPagar

        empresa_id = self.request.session.get('empresa_id')
        if not empresa_id:
            return ExtratoMovimento.objects.none()

        # Filtros
        periodo = self.request.GET.get('periodo')
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        situacao = self.request.GET.get('situacao')
        categoria = self.request.GET.get('categoria')
        conta_banco = self.request.GET.get('conta_banco')
        status = self.request.GET.get('status')

        # Lógica de navegação por meses com estado
        hoje = datetime.now().date()
        mes_atual_visualizacao = self.request.session.get('extrato_movimento_mes_atual', hoje.year * 12 + hoje.month)

        # Converter de volta para ano e mês
        ano_atual = mes_atual_visualizacao // 12
        mes_atual = mes_atual_visualizacao % 12
        if mes_atual == 0:
            ano_atual -= 1
            mes_atual = 12

        # Calcular limite (12 meses para trás)
        mes_limite = hoje.year * 12 + hoje.month - 12

        if periodo:
            if periodo == "mes_atual":
                # Reset para mês atual
                mes_atual_visualizacao = hoje.year * 12 + hoje.month
                self.request.session['extrato_movimento_mes_atual'] = mes_atual_visualizacao
                ano_atual = hoje.year
                mes_atual = hoje.month
            elif periodo == "mes_anterior":
                # Decrementar mês (navegar para trás)
                if mes_atual_visualizacao > mes_limite:
                    mes_atual_visualizacao -= 1
                    self.request.session['extrato_movimento_mes_atual'] = mes_atual_visualizacao

                    # Recalcular ano e mês
                    ano_atual = mes_atual_visualizacao // 12
                    mes_atual = mes_atual_visualizacao % 12
                    if mes_atual == 0:
                        ano_atual -= 1
                        mes_atual = 12

        # Aplicar filtro do mês atual sendo visualizado apenas se especificado
        if periodo in ["mes_atual", "mes_anterior"]:
            # Primeiro e último dia do mês sendo visualizado
            primeiro_dia_mes = date(ano_atual, mes_atual, 1)
            ultimo_dia_mes = date(ano_atual, mes_atual, monthrange(ano_atual, mes_atual)[1])
            data_inicio = primeiro_dia_mes
            data_fim = ultimo_dia_mes

        # Buscar movimentos já registrados
        movimentos_registrados = ExtratoMovimento.objects.filter(empresa_id=empresa_id)

        # Aplicar filtros aos movimentos registrados
        if data_inicio:
            movimentos_registrados = movimentos_registrados.filter(data_baixa__gte=data_inicio)
        if data_fim:
            movimentos_registrados = movimentos_registrados.filter(data_baixa__lte=data_fim)
        if situacao:
            movimentos_registrados = movimentos_registrados.filter(situacao=situacao)
        if categoria:
            movimentos_registrados = movimentos_registrados.filter(categoria_id=categoria)
        if conta_banco:
            movimentos_registrados = movimentos_registrados.filter(conta_banco_id=conta_banco)

        # Buscar contas a receber não baixadas (não conciliadas)
        #contas_receber_pendentes = ContaAReceber.objects.filter(
        #    empresa_id=empresa_id,
        #    status__in=['pendente', 'vencido']
        #)

        # Aplicar filtros de data às contas a receber
        # if data_inicio:
        #     contas_receber_pendentes = contas_receber_pendentes.filter(data_vencimento__gte=data_inicio)
        # if data_fim:
        #     contas_receber_pendentes = contas_receber_pendentes.filter(data_vencimento__lte=data_fim)

        # Buscar contas a pagar não baixadas
        contas_pagar_pendentes = []
        try:
            contas_pagar_pendentes = ContasaPagar.objects.filter(
                empresa_id=empresa_id,
                status__in=['pendente', 'vencido']
            )

            # Aplicar filtros de data às contas a pagar
            if data_inicio:
                contas_pagar_pendentes = contas_pagar_pendentes.filter(dtvenc__gte=data_inicio)
            if data_fim:
                contas_pagar_pendentes = contas_pagar_pendentes.filter(dtvenc__lte=data_fim)
        except:
            # Se não existir o modelo ContasaPagar, continua sem erro
            contas_pagar_pendentes = []

        # Combinar todos os lançamentos em uma lista unificada
        lancamentos_combinados = []

        # Adicionar movimentos registrados
        for movimento in movimentos_registrados:
            lancamentos_combinados.append({
                'tipo': 'movimento_registrado',
                'objeto': movimento,
                'data': movimento.data_baixa,
                'descricao': movimento.descricao,
                'valor': movimento.valor,
                'saldo': movimento.saldo,
                'situacao': movimento.situacao,
                'conciliado': True,  # Movimentos registrados são considerados conciliados
                'origem': str(movimento.conta_banco) if movimento.conta_banco else 'N/A'
            })

        # Adicionar contas a receber pendentes
        # for conta in contas_receber_pendentes:
        #     # Verificar se a conta foi baixada (paga)
        #     conciliado = conta.status == 'pago'
        #     lancamentos_combinados.append({
        #         'tipo': 'conta_receber',
        #         'objeto': conta,
        #         'data': conta.data_vencimento,
        #         'descricao': f'Conta a Receber - {conta.cliente}',
        #         'valor': conta.valor_a_receber,
        #         'saldo': 0,  # Será calculado depois
        #         'situacao': conta.status,
        #         'conciliado': conciliado,  # Só conciliado se pago
        #         'origem': 'N/A'
        #     })

        # Adicionar contas a pagar pendentes
        for conta in contas_pagar_pendentes:
            # Verificar se a conta foi baixada (paga)
            conciliado = conta.status == 'pago'
            lancamentos_combinados.append({
                'tipo': 'conta_pagar',
                'objeto': conta,
                'data': conta.dtvenc,
                'descricao': f'Conta a Pagar - {conta.fornecedor.razao if conta.fornecedor else "N/A"}',
                'valor': -conta.valorDoc,  # Valor negativo para saídas
                'saldo': 0,  # Será calculado depois
                'situacao': conta.status,
                'conciliado': conciliado,  # Só conciliado se pago
                'origem': 'N/A'
            })

        # Ordenar por data (mais recente primeiro)
        lancamentos_combinados.sort(key=lambda x: x['data'], reverse=True)

        # Aplicar filtro de status (conciliado/pendente) aos itens combinados
        if status == 'conciliado':
            lancamentos_combinados = [m for m in lancamentos_combinados if m['conciliado']]
        elif status == 'pendente':
            lancamentos_combinados = [m for m in lancamentos_combinados if not m['conciliado']]

        # Calcular saldos progressivos - só incluir conciliados
        saldo_atual = 0
        for lancamento in reversed(lancamentos_combinados):
            if lancamento['tipo'] == 'movimento_registrado':
                # Para movimentos registrados, usar o saldo já calculado
                saldo_atual = lancamento['objeto'].saldo
            elif lancamento['conciliado']:
                # Só incluir no saldo se estiver conciliado
                saldo_atual += lancamento['valor']
            # Se não conciliado, o saldo permanece o mesmo
            lancamento['saldo'] = saldo_atual

        return lancamentos_combinados

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Estatísticas
        movimentos = self.get_queryset()
        context['total_entradas'] = sum(m['valor'] for m in movimentos if m['valor'] > 0 and m['conciliado'])
        context['total_saidas'] = sum(abs(m['valor']) for m in movimentos if m['valor'] < 0 and m['conciliado'])
        context['saldo_atual'] = movimentos[0]['saldo'] if movimentos else 0

        # Filtros para o template
        periodo = self.request.GET.get('periodo', '')
        context['filtros'] = {
            'periodo': periodo,
            'data_inicio': self.request.GET.get('data_inicio', ''),
            'data_fim': self.request.GET.get('data_fim', ''),
            'situacao': self.request.GET.get('situacao', ''),
            'categoria': self.request.GET.get('categoria', ''),
            'conta_banco': self.request.GET.get('conta_banco', ''),
            'status': self.request.GET.get('status', ''),
        }

        # Categorias para o filtro
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            from categoria.models import Categoria
            context['categorias'] = Categoria.objects.filter(empresa_id=empresa_id).order_by('nome')

        # Contas bancárias para transferência
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:

            context['contas_bancarias'] = ContaBancaria.objects.filter(
                empresa_id=empresa_id,
                status='A'
            ).order_by('banco__nome')

        # Informações sobre navegação por meses
        hoje = datetime.now().date()
        mes_atual_visualizacao = self.request.session.get('extrato_movimento_mes_atual', hoje.year * 12 + hoje.month)

        # Converter de volta para ano e mês
        ano_atual = mes_atual_visualizacao // 12
        mes_atual = mes_atual_visualizacao % 12
        if mes_atual == 0:
            ano_atual -= 1
            mes_atual = 12

        # Calcular limite (12 meses para trás)
        mes_limite = hoje.year * 12 + hoje.month - 12

        # Determinar o texto do período selecionado
        periodo_texto = ''
        if periodo in ["mes_atual", "mes_anterior"] or not periodo:
            import calendar
            nome_mes = calendar.month_name[mes_atual]
            periodo_texto = f"{nome_mes} {ano_atual}"

        # Determinar se pode navegar para trás
        pode_navegar_anterior = mes_atual_visualizacao > mes_limite

        context['periodo_texto'] = periodo_texto
        context['pode_navegar_anterior'] = pode_navegar_anterior

        return context

class LancamentoUpdateView(UpdateView):
    model = Lancamento
    form_class = LancamentoForm
    template_name = 'extrato/lancamento_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            kwargs['empresa_id'] = empresa_id
        return kwargs

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            from empresa.models import Empresa
            try:
                empresa_logada = Empresa.objects.get(id=empresa_id)
                form.instance.empresa = empresa_logada
            except Empresa.DoesNotExist:
                pass
        return super().form_valid(form)

    def get_success_url(self):
        # Preservar os filtros aplicados na URL de redirecionamento
        url = reverse("extrato:lancamento_list")
        query_params = self.request.GET.urlencode()
        if query_params:
            url += '?' + query_params
        return url

class LancamentoDeleteView(DeleteView):
    model = Lancamento
    template_name = 'extrato/lancamento_confirm_delete.html'

    def get_queryset(self):
        """Filtrar lançamentos pela empresa do usuário"""
        queryset = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)
        return queryset

    def get_success_url(self):
        # Preservar os filtros aplicados na URL de redirecionamento
        url = reverse("extrato:lancamento_list")
        query_params = self.request.GET.urlencode()
        if query_params:
            url += '?' + query_params
        return url

class UploadOFXView(View):
    def get(self, request):
        empresa_id = request.session.get('empresa_id')
        form = UploadOFXForm(empresa_id=empresa_id) if empresa_id else UploadOFXForm()
        return render(request, "extrato/upload_ofx.html", {"form": form})

    def post(self, request):
        empresa_id = request.session.get('empresa_id')
        form = UploadOFXForm(request.POST, request.FILES, empresa_id=empresa_id) if empresa_id else UploadOFXForm(request.POST, request.FILES)
        if form.is_valid():
            ea = form.save(commit=False)
            ea.tipo = "OFX"
            ea.save()
            try:
                created, skipped = import_ofx(ea.conta, ea.arquivo, extrato_arquivo=ea)
                if created == 0 and skipped > 0:
                    # Todos os lançamentos são duplicados: remove arquivo e qualquer lançamento criado
                    nome_arquivo = getattr(ea.arquivo, "name", "") or ""
                    Lancamento.objects.filter(extrato_arquivo=ea).delete()
                    ea.delete()
                    return render(request, "extrato/import_error.html", {
                        "error_type": "duplicado",
                        "message": f"Todos os {skipped} lançamentos do arquivo já foram importados anteriormente.",
                        "arquivo": nome_arquivo
                    })
                messages.success(request, f"OFX processado: {created} lançamento(s) em prévia, {skipped} pulado(s) (duplicados). Revise e confirme a importação.")
                return redirect("extrato:extrato_previa", extrato_arquivo_id=ea.id)
            except ValueError as e:
                messages.error(request, f"Erro na importação: {e}")
                ea.delete()
                return render(request, "extrato/upload_ofx.html", {"form": form})
        return render(request, "extrato/upload_ofx.html", {"form": form})

class UploadPDFView(View):
    def get(self, request):
        empresa_id = request.session.get('empresa_id')
        form = UploadPDFForm(empresa_id=empresa_id) if empresa_id else UploadPDFForm()
        return render(request, "extrato/upload_pdf.html", {"form": form})

    def post(self, request):
        empresa_id = request.session.get('empresa_id')
        form = UploadPDFForm(request.POST, request.FILES, empresa_id=empresa_id) if empresa_id else UploadPDFForm(request.POST, request.FILES)
        if form.is_valid():
            ea = form.save(commit=False)
            ea.tipo = "PDF"
            ea.save()
            try:
                created, skipped = import_pdf(ea.conta, ea.arquivo, extrato_arquivo=ea)
                if created == 0 and skipped > 0:
                    nome_arquivo = getattr(ea.arquivo, "name", "") or ""
                    Lancamento.objects.filter(extrato_arquivo=ea).delete()
                    ea.delete()
                    return render(request, "extrato/import_error.html", {
                        "error_type": "duplicado",
                        "message": f"Todos os {skipped} lançamentos do arquivo já foram importados anteriormente.",
                        "arquivo": nome_arquivo
                    })
                messages.success(request, f"PDF processado: {created} lançamento(s) em prévia, {skipped} pulado(s). Revise e confirme a importação.")
                return redirect("extrato:extrato_previa", extrato_arquivo_id=ea.id)
            except Exception as e:
                messages.error(request, f"Falha ao processar PDF: {e}")
                ea.delete()
                return render(request, "extrato/upload_pdf.html", {"form": form})
        return render(request, "extrato/upload_pdf.html", {"form": form})


class ExtratoPreviaView(ListView):
    """Prévia dos lançamentos do arquivo OFX/PDF enviado (status Pendente)."""
    model = Lancamento
    template_name = "extrato/extrato_previa.html"
    context_object_name = "lancamentos"
    paginate_by = 50

    def get_queryset(self):
        empresa_id = self.request.session.get("empresa_id")
        extrato_arquivo_id = self.kwargs.get("extrato_arquivo_id")
        if not empresa_id or not extrato_arquivo_id:
            return Lancamento.objects.none()
        return (
            Lancamento.objects.filter(
                empresa_id=empresa_id,
                extrato_arquivo_id=extrato_arquivo_id,
            )
            .select_related("conta", "banco")
            .order_by("data", "criado_em")
        )

    def get_context_data(self, **kwargs):
        from django.db.models import Sum, Count

        ctx = super().get_context_data(**kwargs)
        extrato_arquivo_id = self.kwargs.get("extrato_arquivo_id")
        empresa_id = self.request.session.get("empresa_id")
        qs = Lancamento.objects.filter(
            empresa_id=empresa_id,
            extrato_arquivo_id=extrato_arquivo_id,
        )
        total_creditos = qs.filter(valor__gt=0).aggregate(s=Sum("valor"))["s"] or Decimal("0")
        total_debitos = qs.filter(valor__lt=0).aggregate(s=Sum("valor"))["s"] or Decimal("0")
        contagem_status = dict(
            qs.values("status_importacao").annotate(c=Count("id")).values_list("status_importacao", "c")
        )
        ctx["extrato_arquivo"] = get_object_or_404(
            ExtratoArquivo,
            id=extrato_arquivo_id,
            conta__empresa_id=empresa_id,
        )
        ctx["total_creditos"] = total_creditos
        ctx["total_debitos"] = total_debitos
        ctx["contagem_status"] = contagem_status
        ctx["extrato_arquivo_id"] = extrato_arquivo_id
        return ctx


class ConfirmarImportacaoView(View):
    """Atualiza lançamentos pendentes do arquivo para status Importado e redireciona para a lista."""
    def post(self, request, extrato_arquivo_id):
        empresa_id = request.session.get("empresa_id")
        if not empresa_id:
            messages.error(request, "Nenhuma empresa selecionada.")
            return redirect("extrato:lancamento_list")
        ea = get_object_or_404(
            ExtratoArquivo,
            id=extrato_arquivo_id,
            conta__empresa_id=empresa_id,
        )
        atualizados = Lancamento.objects.filter(
            extrato_arquivo=ea,
            status_importacao="P",
        ).update(status_importacao="I")
        messages.success(request, f"Importação confirmada: {atualizados} lançamento(s) marcado(s) como importado(s).")
        return redirect("extrato:lancamento_list")


class ContaBancariaListView(ListView):
    """Lista de contas bancárias (somente cadastro, sem lançamentos)."""
    model = ContaBancaria
    template_name = "extrato/conta_bancaria_list.html"
    context_object_name = "contas"
    paginate_by = 20

    def get_queryset(self):
        empresa_id = self.request.session.get("empresa_id")
        if not empresa_id:
            return ContaBancaria.objects.none()
        return ContaBancaria.objects.filter(empresa_id=empresa_id).select_related("banco").order_by("banco__nome", "agencia", "conta")


class ContaBancariaCreateView(CreateView):
    model = ContaBancaria
    form_class = ContaBancariaForm
    template_name = "extrato/conta_bancaria_form.html"
    success_url = reverse_lazy("extrato:conta_bancaria_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa_id"] = self.request.session.get("empresa_id")
        return kwargs

    def form_valid(self, form):
        empresa_id = self.request.session.get("empresa_id")
        if empresa_id:
            from empresa.models import Empresa
            try:
                form.instance.empresa = Empresa.objects.get(id=empresa_id)
            except Empresa.DoesNotExist:
                pass
        return super().form_valid(form)


class ContaBancariaUpdateView(UpdateView):
    model = ContaBancaria
    form_class = ContaBancariaForm
    template_name = "extrato/conta_bancaria_form.html"
    context_object_name = "conta"
    success_url = reverse_lazy("extrato:conta_bancaria_list")

    def get_queryset(self):
        empresa_id = self.request.session.get("empresa_id")
        if not empresa_id:
            return ContaBancaria.objects.none()
        return ContaBancaria.objects.filter(empresa_id=empresa_id)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa_id"] = self.request.session.get("empresa_id")
        return kwargs


class ContaBancariaDeleteView(DeleteView):
    model = ContaBancaria
    template_name = "extrato/conta_bancaria_confirm_delete.html"
    context_object_name = "conta"
    success_url = reverse_lazy("extrato:conta_bancaria_list")

    def get_queryset(self):
        empresa_id = self.request.session.get("empresa_id")
        if not empresa_id:
            return ContaBancaria.objects.none()
        return ContaBancaria.objects.filter(empresa_id=empresa_id)

    def delete(self, request, *args, **kwargs):
        result = super().delete(request, *args, **kwargs)
        messages.success(request, "Conta bancária excluída.")
        return result


class ConciliarView(View):
    """Cria lançamentos individuais no ExtratoMovimento para cada relatório recebíveis relacionado aos lançamentos selecionados."""
    def post(self, request):
        ids = request.POST.getlist("lancamentos")  # lista de IDs selecionados na tela
        obs = request.POST.get("observacao") or ""
        empresa_id = request.session.get('empresa_id')
        total_movimentos_criados = 0

        with transaction.atomic():
            for lancamento_id in ids:
                lancamento = Lancamento.objects.get(id=lancamento_id)

                # Tentar extrair IDs dos relatórios do histórico
                relatorio_ids = []
                if "Relatórios: " in lancamento.historico:
                    relatorios_part = lancamento.historico.split("Relatórios: ")[1].split(" - ")[0]
                    relatorio_ids = [int(id.strip()) for id in relatorios_part.split(", ") if id.strip().isdigit()]

                # Buscar relatórios pelos IDs extraídos ou pelo fitid
                if relatorio_ids:
                    relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        id__in=relatorio_ids,
                        empresa_id=empresa_id,
                        conciliado=False  # Apenas relatórios não conciliados
                    )
                else:
                    relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        identificacao_extrato__icontains=str(lancamento.fitid),
                        empresa_id=empresa_id,
                        conciliado=False  # Apenas relatórios não conciliados
                    )

                # Calcular total do grupo
                total_grupo = sum(rel.valor_liquido for rel in relatorios)

                # Se não encontrou relatórios, tentar conciliar PIX baseado no CPF
                if not relatorios.exists():
                    # Verificar se é uma transação PIX
                    if "PIX RECEBIDO" in lancamento.historico.upper() or "Recebimento Pix" in lancamento.historico:
                        # Extrair CPF mascarado do histórico
                        cpf_mascarado = extrair_cpf_mascarado(lancamento.historico)
                        if cpf_mascarado:
                            # Buscar contas a receber com CPF correspondente
                            from contasareceber.models import ContaAReceber
                            contas_pix = ContaAReceber.objects.filter(
                                empresa_id=empresa_id,
                                cnpj_cpf__isnull=False,
                                status__in=['pendente', 'vencido']
                            )

                            # Filtrar contas onde o CPF mascarado corresponde
                            contas_compatíveis = []
                            for conta in contas_pix:
                                cpf_mascarado_conta = mascarar_cpf_sicoob(conta.cnpj_cpf)
                                if cpf_mascarado_conta == cpf_mascarado:
                                    contas_compatíveis.append(conta)

                            # Se encontrou contas compatíveis, usar a primeira (ou poderia ter lógica mais complexa)
                            if contas_compatíveis:
                                # Usar a primeira conta compatível
                                conta_pix = contas_compatíveis[0]

                                # Verificar se o valor corresponde (com tolerância)
                                valor_tolerancia = Decimal('0.01')
                                if abs(conta_pix.valor_a_receber - lancamento.valor) <= valor_tolerancia:
                                    # Criar descrição para PIX
                                    nome_pix = extrair_nome_pix(lancamento.historico) or "PIX Recebido"
                                    descricao = f"{lancamento.historico} - {nome_pix} - R$ {lancamento.valor:.2f}"

                                    # Criar ExtratoMovimento para PIX
                                    movimento = ExtratoMovimento.objects.create(
                                        empresa_id=empresa_id,
                                        data_baixa=lancamento.data,
                                        descricao=descricao,
                                        valor=lancamento.valor,
                                        situacao='recebido',
                                        conta_banco=lancamento.conta,
                                        lancamento=lancamento,
                                        conta_receber=conta_pix,
                                        saldo=0
                                    )

                                    # Marcar conta como paga
                                    conta_pix.status = 'pago'
                                    conta_pix.data_recebimento = lancamento.data
                                    conta_pix.valor_recebido = lancamento.valor
                                    conta_pix.save()

                                    # Criar baixa da conta a receber
                                    from contasareceber.models import BaixaContaAReceber
                                    baixa = BaixaContaAReceber.objects.create(
                                        conta_a_receber=conta_pix,
                                        empresa_id=empresa_id,
                                        valor_recebido=lancamento.valor,
                                        data_recebimento=lancamento.data,
                                        conta_banco=lancamento.conta
                                    )

                                    # Vincular a baixa ao movimento
                                    movimento.baixa_receber = baixa
                                    movimento.save()

                                    total_movimentos_criados += 1
                                else:
                                    # Valor não corresponde, pular
                                    continue
                            else:
                                # Não encontrou conta com CPF compatível, pular
                                continue
                        else:
                            # Não conseguiu extrair CPF, pular
                            continue
                    else:
                        # Não é PIX nem tem relatórios, pular
                        continue
                else:
                    # Prosseguir com a lógica existente para relatórios

                    # Para cada relatório, criar um movimento individual
                    for relatorio in relatorios:
                        # Construir descrição no formato solicitado
                        descricao = f"{lancamento.historico} {relatorio.nota_fiscal} {relatorio.parcelas}/{relatorio.total_parcelas} - {relatorio.razao} - R$ {lancamento.valor:.2f}"

                        # Criar ExtratoMovimento individual para cada relatório
                        movimento = ExtratoMovimento.objects.create(
                            empresa_id=empresa_id,
                            data_baixa=lancamento.data,  # Data do lançamento
                            descricao=descricao,
                            valor=relatorio.valor_liquido,  # Usar valor_liquido da nota
                            situacao='recebido',
                            conta_banco=lancamento.conta,
                            lancamento=lancamento,
                            conta_receber=relatorio.conta_a_receber,
                            saldo=0  # Será calculado na view
                        )

                        # Marcar relatório como conciliado
                        relatorio.conciliado = True
                        relatorio.identificacao_extrato = str(lancamento.fitid)
                        relatorio.save()

                        # Se há conta a receber, atualizar status
                        if relatorio.conta_a_receber:
                            conta = relatorio.conta_a_receber
                            conta.status = 'pago'
                            conta.data_recebimento = lancamento.data  # Usar data do lançamento
                            conta.valor_recebido = relatorio.valor_bruto  # Usar valor_bruto
                            conta.save()

                            # Criar baixa da conta a receber
                            from contasareceber.models import BaixaContaAReceber
                            baixa = BaixaContaAReceber.objects.create(
                                conta_receber=conta,
                                valor_baixado=relatorio.valor_liquido,  # Usar valor_liquido
                                data_baixa=lancamento.data,  # Usar data do lançamento
                                forma_pagamento='cartao'  # ou outro
                            )

                            # Vincular a baixa ao movimento
                            movimento.baixa_receber = baixa
                            movimento.save()

                        total_movimentos_criados += 1

                # Marcar lançamento como conciliado
                lancamento.conciliado = True
                lancamento.save()

        messages.success(request, f"{total_movimentos_criados} movimentos criados para {len(ids)} lançamentos conciliados.")
        return redirect("extrato:lancamento_list")

class DesconciliarView(View):
    def post(self, request):
        ids = request.POST.getlist("lancamentos")
        empresa_id = request.session.get('empresa_id')

        print("=== DEBUG DesconciliarView ===")
        print(f"Lançamentos selecionados: {ids}")

        # Iniciar processamento de desconciliar

        with transaction.atomic():
            # Buscar os lançamentos a serem desconciliados
            lancamentos = Lancamento.objects.filter(id__in=ids)

            print(f"Lançamentos encontrados: {[f'{l.id} - {l.fitid} - {l.historico}' for l in lancamentos]}")

            # Buscar lançamentos selecionados

            # Verificar se algum lançamento é de conta do tipo CAIXA
            lancamentos_caixa = []
            for lancamento in lancamentos:
                if lancamento.conta and lancamento.conta.tipo == 'CAIXA':
                    lancamentos_caixa.append(lancamento)
                    print(f"Lançamento CAIXA encontrado: {lancamento.id}")

            # Buscar movimentos do extrato relacionados
            movimentos = ExtratoMovimento.objects.filter(lancamento__in=lancamentos)

            # Coletar contas a receber, contas a pagar e baixas relacionadas
            contas_a_receber = []
            contas_a_pagar = []
            baixas_a_deletar = []
            relatorios_a_reverter = []

            for movimento in movimentos:
                if movimento.conta_receber:
                    contas_a_receber.append(movimento.conta_receber)
                if movimento.conta_pagar:
                    contas_a_pagar.append(movimento.conta_pagar)
                if hasattr(movimento, 'baixa_receber') and movimento.baixa_receber:
                    baixas_a_deletar.append(movimento.baixa_receber)

                # Buscar relatórios relacionados ao movimento (através da conta_receber)
                if movimento.conta_receber:
                    relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        conta_a_receber=movimento.conta_receber,
                        empresa_id=empresa_id,
                        conciliado=True
                    )
                    relatorios_a_reverter.extend(relatorios)

            # Buscar relatórios vinculados via identificacao_extrato
            for lancamento in lancamentos:
                if lancamento.fitid:
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
                    relatorios_associados = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        conta_a_receber=conta,
                        empresa_id=empresa_id
                    )
                    for relatorio in relatorios_associados:
                        relatorio.conta_a_receber = None
                        relatorio.save()

                    # Excluir a conta
                    conta.delete()

            # Reverter contas a pagar para status pendente
            for conta in contas_a_pagar:
                conta.status = 'pendente'
                conta.dtPag = None
                conta.valorPago = 0
                conta.desconto = 0
                conta.juros = 0
                conta.save()

            # Reverter contas normais para status cartao ou pendente
            for conta in contas_para_reverter:
                # Verificar se a conta tem relatório de recebíveis (cartão)
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

            # Adicionar pergunta para voltar para pendente
            if contas_para_reverter:
                messages.info(request, f"{len(contas_para_reverter)} conta(s) revertida(s) para status pendente/cartão. Deseja voltar para pendente?")

            # Identificar lançamentos de transferência usando a nova referência
            lancamentos_transferencia = []
            lancamentos_origem_transferencia = []

            print("Verificando lançamentos de transferência...")
            for lancamento in lancamentos:
                print(f"Verificando lançamento {lancamento.id} - FITID: {lancamento.fitid}")
                # Verificar se é um lançamento de destino (tem referência para origem)
                if lancamento.lancamento_origem_transferencia:
                    lancamentos_transferencia.append(lancamento)
                    print(f"Lançamento {lancamento.id} é destino de transferência")
                    # IMPORTANTE: Quando selecionar destino, também devemos incluir a origem para desconciliar
                    if lancamento.lancamento_origem_transferencia not in lancamentos_origem_transferencia:
                        lancamentos_origem_transferencia.append(lancamento.lancamento_origem_transferencia)
                        print(f"Adicionado origem {lancamento.lancamento_origem_transferencia.id} à lista (porque destino foi selecionado)")
                # Verificar se é um lançamento de origem (tem lançamentos destino)
                elif lancamento.lancamentos_destino_transferencia.exists():
                    lancamentos_origem_transferencia.append(lancamento)
                    print(f"Lançamento {lancamento.id} é origem de transferência")
                    # Adicionar todos os lançamentos destino relacionados
                    for destino in lancamento.lancamentos_destino_transferencia.all():
                        if destino not in lancamentos_transferencia:
                            lancamentos_transferencia.append(destino)
                    
                            print(f"Adicionado destino {destino.id} à lista")

            print(f"Lançamentos de transferência identificados: {[l.id for l in lancamentos_transferencia]}")
            print(f"Lançamentos origem transferência: {[l.id for l in lancamentos_origem_transferencia]}")

            # Identificar lançamentos relacionados a transferências

            # Para lançamentos de conta CAIXA: excluir lançamento e movimentos
            if lancamentos_caixa:
                # Excluir movimentos relacionados aos lançamentos de caixa
                ExtratoMovimento.objects.filter(lancamento__in=lancamentos_caixa).delete()
                # Excluir os lançamentos de caixa
                lancamentos_caixa_ids = [l.id for l in lancamentos_caixa]
                Lancamento.objects.filter(id__in=lancamentos_caixa_ids).delete()
                messages.info(request, f"{len(lancamentos_caixa)} lançamento(s) de conta CAIXA foram excluídos.")

            # Para lançamentos de transferência: aplicar regras específicas
            if lancamentos_transferencia or lancamentos_origem_transferencia:
                print("Processando lançamentos de transferência...")
                # Separar lançamentos originais e destino baseado na identificação anterior
                lancamentos_destino_transferencia = []
                lancamentos_origem_transferencia_finais = []

                # Incluir tanto os destinos quanto as origens identificadas
                todos_lancamentos_transf = lancamentos_transferencia + lancamentos_origem_transferencia

                for lancamento_transf in todos_lancamentos_transf:
                    print(f"Processando transferência {lancamento_transf.id} - FITID: {lancamento_transf.fitid}")
                    if lancamento_transf.fitid and lancamento_transf.fitid.startswith('TRANSF-'):
                        # É um lançamento de destino (criado automaticamente)
                        lancamentos_destino_transferencia.append(lancamento_transf)
                        print(f"Identificado como destino: {lancamento_transf.id}")
                    else:
                        # É um lançamento original do extrato bancário
                        lancamentos_origem_transferencia_finais.append(lancamento_transf)
                        print(f"Identificado como origem: {lancamento_transf.id}")

                # Para lançamentos de destino: excluir lançamento e movimentos
                if lancamentos_destino_transferencia:
                    print(f"Excluindo {len(lancamentos_destino_transferencia)} lançamentos de destino...")
                    # Excluir movimentos relacionados aos lançamentos de destino
                    ExtratoMovimento.objects.filter(lancamento__in=lancamentos_destino_transferencia).delete()
                    # Excluir os lançamentos de destino
                    Lancamento.objects.filter(id__in=[l.id for l in lancamentos_destino_transferencia]).delete()
                    messages.info(request, f"{len(lancamentos_destino_transferencia)} lançamento(s) de destino de transferência foram excluídos.")

                # Para lançamentos originais: apenas desconciliar e excluir movimentos
                if lancamentos_origem_transferencia_finais:
                    print(f"Desconciliando {len(lancamentos_origem_transferencia_finais)} lançamentos originais...")
                    # Excluir movimentos relacionados aos lançamentos originais
                    ExtratoMovimento.objects.filter(lancamento__in=lancamentos_origem_transferencia_finais).delete()
                    # IMPORTANTE: Quando selecionamos destino, devemos desconciliar a origem também
                    # Desconciliar os lançamentos originais
                    Lancamento.objects.filter(id__in=[l.id for l in lancamentos_origem_transferencia_finais]).update(conciliado=False)
                    messages.info(request, f"{len(lancamentos_origem_transferencia_finais)} lançamento(s) original(is) de transferência foram desconciliados.")

            # Deletar os movimentos do extrato (todos os movimentos restantes)
            # IMPORTANTE: Só deletar movimentos que não sejam de conta CAIXA ou transferência
            movimentos_para_deletar = movimentos.exclude(
                lancamento__in=lancamentos_caixa + lancamentos_transferencia + lancamentos_origem_transferencia
            )
            movimentos_para_deletar.delete()

            # Desconciliar os lançamentos restantes (não-CAIXA e não-transferência)
            # IMPORTANTE: Para transferências, quando o destino é selecionado, devemos desconciliar a origem
            # Quando a origem é selecionada, apenas desconciliar a origem (destinos já foram excluídos)
            lancamentos_para_desconciliar = lancamentos.exclude(
                id__in=[l.id for l in lancamentos_caixa] + [l.id for l in lancamentos_transferencia]  # Excluir apenas CAIXA e destinos de transferência
            )
            print(f"Lançamentos para desconciliar: {[l.id for l in lancamentos_para_desconciliar]}")

            # IMPORTANTE: Para lançamentos de origem de transferência que foram incluídos automaticamente,
            # devemos garantir que eles sejam desconciliados mesmo que não tenham sido selecionados diretamente
            lancamentos_origem_para_desconciliar = []
            for lancamento in lancamentos_para_desconciliar:
                if lancamento.lancamento_origem_transferencia and lancamento.lancamento_origem_transferencia not in lancamentos_para_desconciliar:
                    lancamentos_origem_para_desconciliar.append(lancamento.lancamento_origem_transferencia)

            # Adicionar as origens não selecionadas à lista de desconciliar
            if lancamentos_origem_para_desconciliar:
                lancamentos_para_desconciliar = list(lancamentos_para_desconciliar) + lancamentos_origem_para_desconciliar
                print(f"Adicionadas origens de transferência para desconciliar: {[l.id for l in lancamentos_origem_para_desconciliar]}")

            lancamentos_para_desconciliar.update(conciliado=False)

            # Finalizar processamento

        messages.success(request, f"{len(ids)} lançamentos processados com sucesso. Contas a receber e relatórios revertidos.")
        return redirect("extrato:lancamento_list")


class DetalhesConciliacaoView(View):
    """View para buscar detalhes da conciliação para exibir no modal"""

    def get(self, request, tipo, pk):
        """
        Retorna detalhes da conciliação em JSON
        tipo: 'nota' ou 'conta'
        pk: ID da nota ou conta
        """
        from contasareceber.models import ContaAReceber
        from notasfiscais.models import NotaFiscalServico

        detalhes = {}

        if tipo == 'nota':
            try:
                nota = NotaFiscalServico.objects.get(pk=pk)
                detalhes['nota'] = {
                    'numero': nota.numero_nota,
                    'cliente': nota.cliente,
                    'valor_liquido': str(nota.valor_liquido),
                    'status_conciliacao': nota.get_status_conciliacao_display(),
                    'data_emissao': nota.data_emissao.strftime('%d/%m/%Y') if nota.data_emissao else None
                }

                # Buscar contas a receber relacionadas
                contas = ContaAReceber.objects.filter(nota=nota)
                detalhes['contas'] = []
                for conta in contas:
                    detalhes['contas'].append({
                        'id': conta.id,
                        'cliente': conta.cliente,
                        'valor_a_receber': str(conta.valor_a_receber),
                        'status': conta.get_status_display(),
                        'data_recebimento': conta.data_recebimento.strftime('%d/%m/%Y') if conta.data_recebimento else None
                    })

                # Buscar movimentos relacionados
                movimentos = ExtratoMovimento.objects.filter(conta_receber__nota=nota)
                detalhes['movimentos'] = []
                for movimento in movimentos:
                    detalhes['movimentos'].append({
                        'id': movimento.id,
                        'data_baixa': movimento.data_baixa.strftime('%d/%m/%Y'),
                        'valor': str(movimento.valor),
                        'situacao': movimento.get_situacao_display(),
                        'lancamento': {
                            'id': movimento.lancamento.id if movimento.lancamento else None,
                            'data': movimento.lancamento.data.strftime('%d/%m/%Y') if movimento.lancamento else None,
                            'historico': movimento.lancamento.historico if movimento.lancamento else None,
                            'valor': str(movimento.lancamento.valor) if movimento.lancamento else None
                        } if movimento.lancamento else None
                    })

            except NotaFiscalServico.DoesNotExist:
                return JsonResponse({'error': 'Nota fiscal não encontrada'}, status=404)

        elif tipo == 'conta':
            try:
                conta = ContaAReceber.objects.get(pk=pk)
                detalhes['conta'] = {
                    'id': conta.id,
                    'cliente': conta.cliente,
                    'valor_a_receber': str(conta.valor_a_receber),
                    'status': conta.get_status_display(),
                    'data_recebimento': conta.data_recebimento.strftime('%d/%m/%Y') if conta.data_recebimento else None
                }

                # Nota fiscal relacionada
                if conta.nota:
                    detalhes['nota'] = {
                        'numero': conta.nota.numero_nota,
                        'cliente': conta.nota.cliente,
                        'valor_liquido': str(conta.nota.valor_liquido),
                        'status_conciliacao': conta.nota.get_status_conciliacao_display()
                    }

                # Movimentos relacionados
                movimentos = ExtratoMovimento.objects.filter(conta_receber=conta)
                detalhes['movimentos'] = []
                for movimento in movimentos:
                    detalhes['movimentos'].append({
                        'id': movimento.id,
                        'data_baixa': movimento.data_baixa.strftime('%d/%m/%Y'),
                        'valor': str(movimento.valor),
                        'situacao': movimento.get_situacao_display(),
                        'lancamento': {
                            'id': movimento.lancamento.id if movimento.lancamento else None,
                            'data': movimento.lancamento.data.strftime('%d/%m/%Y') if movimento.lancamento else None,
                            'historico': movimento.lancamento.historico if movimento.lancamento else None,
                            'valor': str(movimento.lancamento.valor) if movimento.lancamento else None
                        } if movimento.lancamento else None
                    })

            except ContaAReceber.DoesNotExist:
                return JsonResponse({'error': 'Conta a receber não encontrada'}, status=404)

        return JsonResponse(detalhes)

@login_required
def transferir_view(request):
    """View para processar transferência baseada em lançamento do extrato bancário"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:lista')

    # Aplicar os filtros da tela de listagem para verificar se o lançamento está nos resultados filtrados
    lancamentos_filtrados = aplicar_filtros_lancamento_list(Lancamento.objects.all(), request)

    # Obter o ID do lançamento da URL ou parâmetro
    lancamento_id = request.GET.get('lancamento_id')
    lancamento = None

    if lancamento_id:
        try:
            lancamento = Lancamento.objects.get(id=lancamento_id, empresa_id=empresa_id)

            # Verificar se o lançamento está nos resultados filtrados atuais
            if not lancamentos_filtrados.filter(id=lancamento_id).exists():
                messages.warning(request, 'O lançamento selecionado não está nos resultados filtrados atuais.')
                return redirect('extrato:lancamento_list')

        except Lancamento.DoesNotExist:
            messages.error(request, 'Lançamento não encontrado.')
            return redirect('extrato:lancamento_list')

    if request.method == 'POST':
        # Salvar filtros na sessão antes de processar
        request.session['extrato_filtros'] = request.GET.urlencode()
        form = TransferenciaForm(request.POST, empresa_id=empresa_id, lancamento=lancamento)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Dados do formulário
                    conta_origem = lancamento.conta  # Conta do extrato bancário
                    conta_destino = form.cleaned_data['conta_destino']
                    valor = lancamento.valor  # Valor do extrato bancário
                    data_transferencia = lancamento.data  # Data do extrato bancário
                    descricao = f'Origem {conta_origem} para destino {conta_destino}'

                    # Criar 2 lançamentos no ExtratoMovimento conforme regras

                    # REF A CONTA DE ORIGEM - Usar o lançamento existente do extrato bancário
                    # Não criar novo lançamento, apenas o movimento
                    movimento_origem = ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=data_transferencia,
                        descricao=descricao,
                        valor=valor,  # Valor positivo do extrato
                        situacao='pago',  # Transferência de saída
                        conta_banco=conta_origem,
                        lancamento=lancamento,  # Vincular ao lançamento existente do extrato
                        categoria=None
                    )

                    # REF A CONTA DE DESTINO - Criar lançamento na tabela Lancamento
                    # Gerar um fitid único para evitar duplicatas
                    import uuid
                    fitid_unico = f"TRANSF-{uuid.uuid4().hex[:8]}"

                    lancamento_destino = Lancamento.objects.create(
                        empresa_id=empresa_id,
                        data=data_transferencia,
                        valor=valor * -1,  # Valor negativo
                        historico=descricao,
                        documento='',
                        fitid=fitid_unico,  # FITID único para evitar duplicatas
                        conta=conta_destino,
                        banco=conta_destino.banco,  # Adicionar banco
                        conciliado=True,
                        lancamento_origem_transferencia=lancamento  # Referência ao lançamento original
                    )

                    # REF A CONTA DE DESTINO - Movimento
                    movimento_destino = ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=data_transferencia,
                        descricao=descricao,
                        valor=valor * -1,  # Valor negativo
                        situacao='recebido',  # Transferência de entrada
                        conta_banco=conta_destino,
                        lancamento=lancamento_destino,  # Vincular ao novo lançamento
                        categoria=None
                    )

                    # Marcar o lançamento como conciliado
                    lancamento.conciliado = True
                    lancamento.save()

                    messages.success(
                        request,
                        f'Transferência realizada com sucesso! '
                        f'Valor: R$ {valor:.2f} | '
                        f'De: {conta_origem} | '
                        f'Para: {conta_destino}'
                    )

                    # Redirecionar com filtros preservados
                    filtros_salvos = request.session.get('extrato_filtros', '')
                    url = reverse('extrato:lancamento_list')
                    if filtros_salvos:
                        url += '?' + filtros_salvos
                    return redirect(url)

            except Exception as e:
                messages.error(request, f'Erro ao processar transferência: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

    else:
        # GET request - mostrar formulário
        form = TransferenciaForm(empresa_id=empresa_id, lancamento=lancamento)

    context = {
        'form': form,
        'lancamento': lancamento,
        'title': 'Transferência baseada em Extrato Bancário'
    }

    return render(request, 'extrato/transferencia.html', context)


@login_required
def detalhes_modal(request, tipo, id):
    """
    View para fornecer dados ao modal de detalhes
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'error': 'Empresa não selecionada'}, status=400)

    try:
        # Imports necessários
        from notasfiscais.models import NotaFiscalServico
        from contasareceber.models import ContaAReceber
        from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

        # Buscar o objeto baseado no tipo
        if tipo == 'nf':
            obj = NotaFiscalServico.objects.get(id=id, empresa_id=empresa_id)
            nf = obj
        elif tipo == 'conta':
            obj = ContaAReceber.objects.get(id=id, empresa_id=empresa_id)
            nf = obj.nota if obj.nota else None
        elif tipo == 'movimento':
            obj = ExtratoMovimento.objects.select_related(
                'baixa_receber', 'conta_receber', 'conta_receber__nota', 'lancamento', 'conta_banco'
            ).get(id=id, empresa_id=empresa_id)
            lancamento_conciliado = obj.lancamento if obj.lancamento else None
            nf = obj.conta_receber.nota if obj.conta_receber and obj.conta_receber.nota else None
        elif tipo == 'lancamento':
            obj = Lancamento.objects.get(id=id, empresa_id=empresa_id)
            # Buscar todos os movimentos relacionados ao lançamento
            movimentos = (
                ExtratoMovimento.objects.filter(lancamento=obj, empresa_id=empresa_id)
                .order_by('-data_baixa')
                .select_related('baixa_receber')
            )

            # Coletar todas as contas a receber e notas relacionadas
            contas_receber = []
            notas = []

            # Primeiro, buscar contas relacionadas diretamente aos movimentos
            for movimento in movimentos:
                if movimento.conta_receber and movimento.conta_receber not in contas_receber:
                    contas_receber.append(movimento.conta_receber)
                if movimento.conta_receber and movimento.conta_receber.nota and movimento.conta_receber.nota not in notas:
                    notas.append(movimento.conta_receber.nota)

            # Se não encontrou relacionamentos diretos, tentar buscar por fitid/identificacao_extrato
            if not contas_receber and not notas and obj.fitid:
                # Buscar relatórios conciliados com este fitid
                relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(
                    empresa_id=empresa_id,
                    identificacao_extrato__icontains=str(obj.fitid)
                )

                for relatorio in relatorios:
                    if relatorio.conta_a_receber and relatorio.conta_a_receber not in contas_receber:
                        contas_receber.append(relatorio.conta_a_receber)
                    if relatorio.conta_a_receber and relatorio.conta_a_receber.nota and relatorio.conta_a_receber.nota not in notas:
                        notas.append(relatorio.conta_a_receber.nota)

                # Também buscar contas a receber que tenham o fitid no histórico
                contas_por_historico = ContaAReceber.objects.filter(
                    empresa_id=empresa_id,
                    doc__icontains=str(obj.fitid)
                )
                for conta in contas_por_historico:
                    if conta not in contas_receber:
                        contas_receber.append(conta)
                    if conta.nota and conta.nota not in notas:
                        notas.append(conta.nota)

            # Buscar notas fiscais relacionadas diretamente ao histórico do lançamento
            if not notas:
                # Tentar extrair número da nota do histórico
                import re
                numero_match = re.search(r'NF\s*(\d+)', obj.historico, re.IGNORECASE)
                if numero_match:
                    numero_nota = numero_match.group(1)
                    try:
                        nota = NotaFiscalServico.objects.get(
                            empresa_id=empresa_id,
                            numero_nota=numero_nota
                        )
                        if nota not in notas:
                            notas.append(nota)
                            # Buscar contas relacionadas a esta nota
                            contas_da_nota = ContaAReceber.objects.filter(
                                empresa_id=empresa_id,
                                nota=nota
                            )
                            for conta in contas_da_nota:
                                if conta not in contas_receber:
                                    contas_receber.append(conta)
                    except NotaFiscalServico.DoesNotExist:
                        pass
        else:
            return JsonResponse({'error': 'Tipo inválido'}, status=400)

        # Buscar dados relacionados
        if tipo == 'lancamento':
            # Para lançamento, já temos movimentos, contas e notas coletadas acima
            pass
        else:
            # Lógica existente para outros tipos
            conta_receber = None
            movimentos = []
            lancamento_conciliado = None

            if nf:
                # Buscar conta a receber da NF
                from contasareceber.models import ContaAReceber
                conta_receber = ContaAReceber.objects.filter(nota=nf, empresa_id=empresa_id).first()

            if conta_receber:
                # Buscar movimentos da conta a receber
                movimentos = ExtratoMovimento.objects.filter(conta_receber=conta_receber).order_by('-data_baixa')

            if movimentos:
                # Buscar lançamentos conciliados dos movimentos
                lancamentos_ids = [m.lancamento_id for m in movimentos if m.lancamento_id]
                if lancamentos_ids:
                    lancamento_conciliado = Lancamento.objects.filter(id__in=lancamentos_ids).first()

        # Construir HTML do modal
        if tipo == 'lancamento':
            # Para lançamento, mostrar todas as notas, contas e movimentos relacionados
            notas_html = ''.join([f'<p><strong>Número:</strong> {nota.numero_nota} - <strong>Cliente:</strong> {nota.cliente} - <strong>Valor:</strong> R$ {nota.valor_liquido:.2f}</p>' for nota in notas]) if notas else '<p>Nenhuma NF encontrada</p>'
            contas_html = ''.join([f'<p><strong>Cliente:</strong> {conta.cliente} - <strong>Valor:</strong> R$ {conta.valor_a_receber:.2f} - <strong>Status:</strong> {conta.get_status_display()}</p>' for conta in contas_receber]) if contas_receber else '<p>Nenhuma conta encontrada</p>'
            def _html_linha_movimento_extrato(m):
                br = m.baixa_receber
                d = float(br.desconto or 0) if br else 0.0
                j = float(br.juros or 0) if br else 0.0
                t = float(br.tarifas or 0) if br else 0.0
                ajustes = f' — Desconto R$ {d:.2f} | Juros R$ {j:.2f} | Tarifa R$ {t:.2f}'
                return (
                    f'<p><strong>{m.data_baixa.strftime("%d/%m/%Y")}:</strong> R$ {m.valor:.2f}{ajustes} — '
                    f'{m.descricao[:50]}...</p>'
                )

            movimentos_html = (
                ''.join(_html_linha_movimento_extrato(m) for m in movimentos) if movimentos else '<p>Nenhum movimento encontrado</p>'
            )

            # Buscar contas a pagar relacionadas ao lançamento
            contas_pagar = []
            if obj.conciliado:
                movimentos_pagar = ExtratoMovimento.objects.filter(
                    lancamento=obj,
                    empresa_id=empresa_id,
                    conta_pagar__isnull=False
                ).select_related('conta_pagar', 'conta_pagar__fornecedor', 'conta_pagar__categoria')
                contas_pagar = [m.conta_pagar for m in movimentos_pagar if m.conta_pagar]

            contas_pagar_html = ''.join([f'''
                <div class="border rounded p-2 mb-2">
                    <p class="mb-1"><strong>Fornecedor:</strong> {conta.fornecedor.razao if conta.fornecedor else "N/A"}</p>
                    <p class="mb-1"><strong>Descrição:</strong> {conta.descricao[:50]}...</p>
                    <p class="mb-1"><strong>Categoria:</strong> {conta.categoria.nome if conta.categoria else "N/A"}</p>
                    <p class="mb-1"><strong>Valor:</strong> R$ {conta.valorDoc:.2f}</p>
                    <p class="mb-1"><strong>Data Emissão:</strong> {conta.dtEmissao.strftime('%d/%m/%Y') if conta.dtEmissao else 'N/A'}</p>
                    <p class="mb-1"><strong>Data Vencimento:</strong> {conta.dtvenc.strftime('%d/%m/%Y') if conta.dtvenc else 'N/A'}</p>
                    <p class="mb-1"><strong>Data Pagamento:</strong> {conta.dtPag.strftime('%d/%m/%Y') if conta.dtPag else 'N/A'}</p>
                    <p class="mb-1"><strong>Status:</strong> Paga</p>
                    <p class="mb-1"><strong>Documento:</strong> {conta.numdoc or 'N/A'}</p>
                    <p class="mb-1"><strong>Forma Pgto:</strong> {conta.cobranca.descricao if conta.cobranca else 'N/A'}</p>
                </div>
            ''' for conta in contas_pagar]) if contas_pagar else '<p>Nenhuma conta a pagar encontrada</p>'

            html = f"""
            <div class="row">
                <div class="col-md-12">
                    <h5>Lançamento</h5>
                    <p><strong>Data:</strong> {obj.data.strftime('%d/%m/%Y')}</p>
                    <p><strong>Valor:</strong> R$ {obj.valor:.2f}</p>
                    <p><strong>Histórico:</strong> {obj.historico}</p>
                    <p><strong>Conta:</strong> {obj.conta}</p>
                    <p><strong>Status:</strong> {'Conciliado' if obj.conciliado else 'Pendente'}</p>
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-6">
                    <h5>Notas Fiscais Relacionadas</h5>
                    {notas_html}
                </div>
                <div class="col-md-6">
                    <h5>Contas a Receber Relacionadas</h5>
                    {contas_html}
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-6">
                    <h5>Contas a Pagar Relacionadas</h5>
                    {contas_pagar_html}
                </div>
                <div class="col-md-6">
                    <h5>Movimentos do Extrato</h5>
                    {movimentos_html}
                </div>
            </div>
            """
        else:
            # Lógica existente para outros tipos
            # Buscar contas a pagar relacionadas ao movimento
            contas_pagar_relacionadas = []
            if hasattr(obj, 'conta_pagar') and obj.conta_pagar:
                contas_pagar_relacionadas = [obj.conta_pagar]

            contas_pagar_html = ''.join([f'''
                <div class="border rounded p-2 mb-2">
                    <p class="mb-1"><strong>Fornecedor:</strong> {conta.fornecedor.razao if conta.fornecedor else "N/A"}</p>
                    <p class="mb-1"><strong>Descrição:</strong> {conta.descricao[:50]}...</p>
                    <p class="mb-1"><strong>Categoria:</strong> {conta.categoria.nome if conta.categoria else "N/A"}</p>
                    <p class="mb-1"><strong>Valor:</strong> R$ {conta.valorDoc:.2f}</p>
                    <p class="mb-1"><strong>Data Emissão:</strong> {conta.dtEmissao.strftime('%d/%m/%Y') if conta.dtEmissao else 'N/A'}</p>
                    <p class="mb-1"><strong>Data Vencimento:</strong> {conta.dtvenc.strftime('%d/%m/%Y') if conta.dtvenc else 'N/A'}</p>
                    <p class="mb-1"><strong>Data Pagamento:</strong> {conta.dtPag.strftime('%d/%m/%Y') if conta.dtPag else 'N/A'}</p>
                    <p class="mb-1"><strong>Status:</strong> Paga</p>
                    <p class="mb-1"><strong>Documento:</strong> {conta.numdoc or 'N/A'}</p>
                    <p class="mb-1"><strong>Forma Pgto:</strong> {conta.cobranca.descricao if conta.cobranca else 'N/A'}</p>
                </div>
            ''' for conta in contas_pagar_relacionadas]) if contas_pagar_relacionadas else '<p>Nenhuma conta a pagar encontrada</p>'

            # Buscar o lançamento do extrato relacionado ao movimento
            lancamento_extrato = None
            if hasattr(obj, 'lancamento') and obj.lancamento:
                lancamento_extrato = obj.lancamento

            baixa_em = getattr(obj, 'baixa_receber', None)
            if baixa_em is not None:
                desconto_em = float(baixa_em.desconto or 0)
                juros_em = float(baixa_em.juros or 0)
                tarifa_em = float(baixa_em.tarifas or 0)
            else:
                desconto_em = juros_em = tarifa_em = 0.0

            html = f"""
            <div class="row">
                <div class="col-md-6">
                    <h5>Nota Fiscal</h5>
                    {f'<p><strong>Número:</strong> {nf.numero_nota}</p>' if nf else '<p>Nenhuma NF encontrada</p>'}
                    {f'<p><strong>Cliente:</strong> {nf.cliente}</p>' if nf else ''}
                    {f'<p><strong>Valor:</strong> R$ {nf.valor_liquido:.2f}</p>' if nf else ''}
                </div>
                <div class="col-md-6">
                    <h5>Conta a Receber</h5>
                    {f'<p><strong>Cliente:</strong> {conta_receber.cliente}</p>' if conta_receber else '<p>Nenhuma conta encontrada</p>'}
                    {f'<p><strong>Valor:</strong> R$ {conta_receber.valor_a_receber:.2f}</p>' if conta_receber else ''}
                    {f'<p><strong>Status:</strong> {conta_receber.get_status_display()}</p>' if conta_receber else ''}
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-6">
                    <h5>Movimentos do Extrato</h5>
                    <div class="border rounded p-2 mb-2">
                        <p class="mb-1"><strong>Data:</strong> {obj.data_baixa.strftime('%d/%m/%Y')}</p>
                        <p class="mb-1"><strong>Valor:</strong> R$ {obj.valor:.2f}</p>
                        <p class="mb-1"><strong>Desconto:</strong> R$ {desconto_em:.2f}</p>
                        <p class="mb-1"><strong>Juros:</strong> R$ {juros_em:.2f}</p>
                        <p class="mb-1"><strong>Tarifa:</strong> R$ {tarifa_em:.2f}</p>
                        <p class="mb-1"><strong>Descrição:</strong> {obj.descricao[:50]}...</p>
                        <p class="mb-1"><strong>Situação:</strong> {obj.get_situacao_display()}</p>
                        <p class="mb-1"><strong>Conta:</strong> {obj.conta_banco if obj.conta_banco else 'N/A'}</p>
                    </div>
                </div>
                <div class="col-md-6">
                    <h5>Lançamento do Extrato</h5>
                    {f'''
                    <div class="border rounded p-2 mb-2">
                        <p class="mb-1"><strong>Data:</strong> {lancamento_extrato.data.strftime('%d/%m/%Y')}</p>
                        <p class="mb-1"><strong>Valor:</strong> R$ {lancamento_extrato.valor:.2f}</p>
                        <p class="mb-1"><strong>Histórico:</strong> {lancamento_extrato.historico[:50]}...</p>
                        <p class="mb-1"><strong>Conta:</strong> {lancamento_extrato.conta}</p>
                        <p class="mb-1"><strong>Documento:</strong> {lancamento_extrato.documento or 'N/A'}</p>
                        <p class="mb-1"><strong>Status:</strong> {'Conciliado' if lancamento_extrato.conciliado else 'Pendente'}</p>
                    </div>
                    ''' if lancamento_extrato else '<p>Nenhum lançamento do extrato encontrado</p>'}
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-12">
                    <h5>Contas a Pagar Relacionadas</h5>
                    {contas_pagar_html}
                </div>
            </div>
            """

        return JsonResponse({'html': html})

    except Exception as e:
        return JsonResponse({'error': f'Erro interno: {str(e)}'}, status=500)


@login_required
def lancamento_relatorios_view(request, lancamento_id):
    """
    View para mostrar os relatórios de recebíveis conciliados com um lançamento
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:lista')

    # Aplicar os filtros da tela de listagem para verificar se o lançamento está nos resultados filtrados
    lancamentos_filtrados = aplicar_filtros_lancamento_list(Lancamento.objects.all(), request)

    # Verificar se o lançamento está nos resultados filtrados atuais
    if not lancamentos_filtrados.filter(id=lancamento_id).exists():
        messages.warning(request, 'O lançamento selecionado não está nos resultados filtrados atuais.')
        return redirect('extrato:lancamento_list')

    # Buscar o lançamento
    lancamento = get_object_or_404(Lancamento, id=lancamento_id, empresa_id=empresa_id)

    # Buscar relatórios conciliados relacionados a este lançamento
    # Os relatórios têm o campo identificacao_extrato que contém informações do lançamento
    from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

    # Filtrar relatórios que contenham informações deste lançamento
    relatorios_relacionados = RelatorioRecebiveisMaquinaCartao.objects.filter(
        empresa_id=empresa_id,
        conciliado=True,
        identificacao_extrato__icontains=str(lancamento.fitid)
    ).order_by('-data_pagamento')

    # Também buscar através de ExtratoMovimento se existir relação
    movimentos_relacionados = ExtratoMovimento.objects.filter(
        lancamento=lancamento,
        empresa_id=empresa_id
    )

    relatorios_via_movimentos = []
    relatorios_via_conta_receber = []
    if movimentos_relacionados.exists():
        for movimento in movimentos_relacionados:
            if movimento.conta_receber:
                # Buscar relatórios relacionados à conta a receber
                relatorios_conta = RelatorioRecebiveisMaquinaCartao.objects.filter(
                    empresa_id=empresa_id,
                    conta_a_receber=movimento.conta_receber
                )
                relatorios_via_conta_receber.extend(relatorios_conta)

                if movimento.conta_receber.nota:
                    # Buscar relatórios relacionados à nota fiscal
                    relatorios_nota = RelatorioRecebiveisMaquinaCartao.objects.filter(
                        empresa_id=empresa_id,
                        nota_fiscal=movimento.conta_receber.nota.numero_nota
                    )
                    relatorios_via_movimentos.extend(relatorios_nota)

    # Combinar e remover duplicatas
    todos_relatorios = list(relatorios_relacionados) + relatorios_via_movimentos
    relatorios_unicos = []
    ids_vistos = set()

    for relatorio in todos_relatorios:
        if relatorio.id not in ids_vistos:
            relatorios_unicos.append(relatorio)
            ids_vistos.add(relatorio.id)

    # Ordenar por data de pagamento (mais recente primeiro)
    relatorios_unicos.sort(key=lambda x: x.data_pagamento, reverse=True)

    # Calcular totais
    total_bruto = sum(rel.valor_bruto for rel in relatorios_unicos)
    total_tarifa = sum(rel.taxa_maquinha for rel in relatorios_unicos)

    context = {
        'lancamento': lancamento,
        'relatorios': relatorios_unicos,
        'total_relatorios': len(relatorios_unicos),
        'total_bruto': total_bruto,
        'total_tarifa': total_tarifa,
        'title': f'Relatórios Conciliados - Lançamento {lancamento.fitid}'
    }

    return render(request, 'extrato/lancamento_relatorios.html', context)


@login_required
def exportar_conciliacao_view(request):
    """
    View para o botão EXPORTAR_CONCILIACAO
    """
    from django.http import HttpResponse
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return HttpResponse("Empresa não selecionada", status=400)

    # Usar a função de filtros para aplicar os mesmos filtros da tela de listagem
    lancamentos = aplicar_filtros_lancamento_list(Lancamento.objects.filter(conciliado=True), request)

    # Gerar o texto de exportação
    linhas = []

    # CNPJ da empresa
    from empresa.models import Empresa
    try:
        empresa = Empresa.objects.get(id=empresa_id)
        if empresa.cnpj:
            linhas.append(f"|0000|{empresa.cnpj}|")
    except Empresa.DoesNotExist:
        pass

    for lancamento in lancamentos:
        movimentos = lancamento.extrato_movimentos.filter(empresa_id=empresa_id)
        num_movimentos = movimentos.count()

        if num_movimentos == 1:
            # Apenas 1 movimento: usar X
            linhas.append("|6000|X||||")
            movimento = movimentos.first()
            data_formatada = lancamento.data.strftime('%d/%m/%Y')
            conta_contabil = lancamento.conta.conta_contabil or ''
            # Para 1 movimento, usar conta_contabil da conta bancária, depois 4900, valor
            valor = abs(lancamento.valor) if lancamento.valor < 0 else lancamento.valor
            valor_formatado = f"{valor:.2f}".replace('.', ',')
            linha = f"|6100|{data_formatada}|{conta_contabil}|4900|{valor_formatado}||{movimento.descricao}||||"
            linhas.append(linha)

        elif num_movimentos > 1:
            # Mais de 1 movimento: usar C se valor < 0, D se valor > 0
            tipo = 'D' if lancamento.valor > 0 else 'C'
            linhas.append(f"|6000|{tipo}||||")
            # Primeiro, a linha do lançamento (extrato bancário)
            data_lancamento = lancamento.data.strftime('%d/%m/%Y')
            valor_lancamento = abs(lancamento.valor) if lancamento.valor < 0 else lancamento.valor
            valor_lancamento_formatado = f"{valor_lancamento:.2f}".replace('.', ',')
            conta1_lanc = lancamento.conta.conta_contabil if lancamento.valor > 0 else ''
            conta2_lanc = lancamento.conta.conta_contabil if lancamento.valor < 0 else ''
            linha_lanc = f"|6100|{data_lancamento}|{conta1_lanc}|{conta2_lanc}|{valor_lancamento_formatado}||{lancamento.historico}||||"
            linhas.append(linha_lanc)
            # Depois, as linhas dos movimentos
            for movimento in movimentos:
                data_formatada = movimento.data_baixa.strftime('%d/%m/%Y')
                valor = abs(movimento.valor) if movimento.valor < 0 else movimento.valor
                valor_formatado = f"{valor:.2f}".replace('.', ',')
                # Para movimentos: 142 se valor < 0, senão vazio; 142 se valor > 0, senão vazio
                conta1 = '142' if movimento.valor < 0 else ''
                conta2 = '142' if movimento.valor > 0 else ''
                linha = f"|6100|{data_formatada}|{conta1}|{conta2}|{valor_formatado}||{movimento.descricao}||||"
                linhas.append(linha)

    # Juntar todas as linhas
    conteudo = '\n'.join(linhas)

    # Retornar como arquivo de texto
    response = HttpResponse(conteudo, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="conciliacao.txt"'
    return response


@login_required
def buscar_contas_conciliacao_multipla(request, lancamento_id):
    """
    View AJAX para buscar contas para conciliação múltipla
    """
    try:
        empresa_id = request.session.get('empresa_id')
        if not empresa_id:
            return JsonResponse({'error': 'Empresa não selecionada'}, status=400)

        if request.method != 'POST':
            return JsonResponse({'error': 'Método não permitido'}, status=405)

        # Buscar o lançamento base
        lancamento_base = get_object_or_404(Lancamento, id=lancamento_id, empresa_id=empresa_id)

        # Parâmetros da busca
        tipo_conta = request.POST.get('tipo_conta', 'receber')
        data_inicio = request.POST.get('data_inicio')
        data_fim = request.POST.get('data_fim')
        cliente_fornecedor = request.POST.get('cliente_fornecedor', '').strip()

        print(f"DEBUG buscar_contas_conciliacao_multipla: tipo_conta={tipo_conta}, empresa_id={empresa_id}")
        print(f"DEBUG POST data: {dict(request.POST)}")
        print(f"DEBUG Raw POST: {request.body.decode('utf-8') if request.body else 'No body'}")

        # Tentar ler dados JSON do corpo da requisição
        import json
        try:
            json_data = json.loads(request.body.decode('utf-8'))
            tipo_conta = json_data.get('tipo_conta', 'receber')
            data_inicio = json_data.get('data_inicio')
            data_fim = json_data.get('data_fim')
            cliente_fornecedor = json_data.get('cliente_fornecedor', '').strip()
            print(f"DEBUG JSON data: {json_data}")
            print(f"DEBUG tipo_conta from JSON: {tipo_conta}")
        except:
            print("DEBUG: Failed to parse JSON from body")
            pass

        # Buscar contas baseado no tipo
        if tipo_conta == 'receber':
            print("DEBUG: Processando contas a receber")
            from contasareceber.models import ContaAReceber
            contas = ContaAReceber.objects.filter(
                empresa_id=empresa_id,
                status__in=['pendente', 'vencido']
            ).select_related('nota')

            # Aplicar filtros de data
            if data_inicio:
                contas = contas.filter(data_vencimento__gte=data_inicio)
            if data_fim:
                contas = contas.filter(data_vencimento__lte=data_fim)

            # Filtro por cliente
            if cliente_fornecedor:
                contas = contas.filter(cliente__razao__icontains=cliente_fornecedor)

            contas_data = []
            for conta in contas[:50]:  # Limitar a 50 resultados
                contas_data.append({
                    'id': conta.id,
                    'cliente': conta.cliente,  # Já é um CharField no modelo
                    'data_emissao': conta.data_emissao.strftime('%d/%m/%Y') if conta.data_emissao else '',
                    'data_vencimento': conta.data_vencimento.strftime('%d/%m/%Y') if conta.data_vencimento else '',
                    'documento': conta.doc or '',
                    'forma_pgto': conta.forma_pagamento.descricao if conta.forma_pagamento else '',
                    'valor': str(conta.valor_a_receber),
                    'valor_liquido': str(conta.valor_a_receber),  # Simplificado
                    'desconto': str(conta.desconto or 0),
                    'juros': str(conta.juros or 0),
                    'tarifas': str(conta.tarifas or 0),
                    'valor_receber': str(conta.get_valor_total_com_ajustes()),
                    'status': conta.get_status_display()
                })

        else:  # contas a pagar
            print("DEBUG: Processando contas a pagar")
            from contasapagar.models import ContasaPagar
            contas = ContasaPagar.objects.filter(
                empresa_id=empresa_id,
                status__in=['pendente', 'vencido']
            ).select_related('fornecedor')

            print(f"DEBUG: Query contas a pagar - empresa_id={empresa_id}, count={contas.count()}")

            # Debug: mostrar algumas contas antes dos filtros
            for conta in contas[:5]:
                print(f"DEBUG: Conta antes filtros - ID: {conta.id}, Fornecedor: {conta.fornecedor.razao if conta.fornecedor else 'N/A'}, Status: {conta.status}, Vencimento: {conta.dtvenc}, Empresa: {conta.empresa_id if hasattr(conta, 'empresa_id') else 'No empresa field'}")

            # Aplicar filtros de data
            if data_inicio:
                contas = contas.filter(dtvenc__gte=data_inicio)
                print(f"DEBUG: Após filtro data_inicio ({data_inicio}) - count={contas.count()}")
            if data_fim:
                contas = contas.filter(dtvenc__lte=data_fim)
                print(f"DEBUG: Após filtro data_fim ({data_fim}) - count={contas.count()}")

            # Filtro por fornecedor
            if cliente_fornecedor:
                contas = contas.filter(fornecedor__razao__icontains=cliente_fornecedor)
                print(f"DEBUG: Após filtro fornecedor ({cliente_fornecedor}) - count={contas.count()}")

            print(f"DEBUG: Após filtros - count={contas.count()}")

            # Verificar se há contas encontradas
            if not contas.exists():
                print("DEBUG: Nenhuma conta a pagar encontrada com os filtros aplicados")
                return JsonResponse({
                    'success': False,
                    'error': 'Nenhuma conta a pagar encontrada com os filtros selecionados.'
                })

            contas_data = []
            for conta in contas[:50]:  # Limitar a 50 resultados
                print(f"DEBUG: Conta a pagar encontrada - ID: {conta.id}, Fornecedor: {conta.fornecedor.razao if conta.fornecedor else 'N/A'}, Valor: {conta.valorDoc}")
                contas_data.append({
                    'id': conta.id,
                    'cliente': conta.fornecedor.razao if conta.fornecedor else 'N/A',
                    'data_emissao': conta.dtEmissao.strftime('%d/%m/%Y') if conta.dtEmissao else '',
                    'data_vencimento': conta.dtvenc.strftime('%d/%m/%Y') if conta.dtvenc else '',
                    'documento': conta.numdoc or '',
                    'forma_pgto': conta.cobranca.descricao if conta.cobranca else '',
                    'valor': str(conta.valorDoc),
                    'valor_liquido': str(conta.valorDoc),  # Simplificado
                    'desconto': '0,00',
                    'juros': '0,00',
                    'tarifas': '0,00',
                    'valor_receber': str(conta.valorDoc),
                    'status': conta.get_status_display()
                })

            print(f"DEBUG: Total contas_data para contas a pagar: {len(contas_data)}")

        print(f"DEBUG: Retornando {len(contas_data)} contas para tipo {tipo_conta}")

        return JsonResponse({
            'success': True,
            'contas': contas_data
        })

    except Exception as e:
        print(f"DEBUG: Erro na busca de contas: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Erro ao buscar contas: {str(e)}'
        }, status=500)

@login_required
def conciliar_multiplo_view(request, lancamento_id):
    """
    View para conciliar múltiplos lançamentos baseado em um lançamento base
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:lista')

    # Buscar o lançamento base
    lancamento_base = get_object_or_404(Lancamento, id=lancamento_id, empresa_id=empresa_id)

    # Aplicar os filtros da tela de listagem para buscar apenas lançamentos filtrados
    lancamentos_filtrados = aplicar_filtros_lancamento_list(Lancamento.objects.all(), request)
    # Verificar se o lançamento base está nos resultados filtrados
    if not lancamentos_filtrados.filter(id=lancamento_id).exists():
        messages.warning(request, 'O lançamento selecionado não está nos resultados filtrados atuais.')
        return redirect('extrato:lancamento_list')

    if request.method == 'POST':
        # Processar a conciliação múltipla
        contas_selecionadas = request.POST.getlist('contas_selecionadas')
        tipo_conta = request.POST.get('tipo_conta', 'receber')

        with transaction.atomic():
            # Marcar lançamento base como conciliado
            lancamento_base.conciliado = True
            lancamento_base.save()

            for conta_id in contas_selecionadas:
                # Buscar valores dos campos da tela
                desconto = request.POST.get(f'desconto_{conta_id}', '0').replace(',', '.')
                juros = request.POST.get(f'juros_{conta_id}', '0').replace(',', '.')
                tarifas = request.POST.get(f'tarifas_{conta_id}', '0').replace(',', '.')

                try:
                    desconto_val = Decimal(desconto) if desconto else Decimal('0')
                    juros_val = Decimal(juros) if juros else Decimal('0')
                    tarifas_val = Decimal(tarifas) if tarifas else Decimal('0')
                except:
                    desconto_val = Decimal('0')
                    juros_val = Decimal('0')
                    tarifas_val = Decimal('0')

                if tipo_conta == 'receber':
                    # Processar contas a receber
                    from contasareceber.models import ContaAReceber
                    conta = get_object_or_404(ContaAReceber, id=conta_id, empresa_id=empresa_id)

                    # Ajustes do formulário ANTES do líquido: get_valor_total_com_ajustes() usa
                    # desconto/juros/tarifas da instância. Ordem errada gerava valor_recebido = valor
                    # nominal (ex. 450) e movimentos somando acima do crédito bancário (ex. 480).
                    conta.desconto = desconto_val
                    conta.juros = juros_val
                    conta.tarifas = tarifas_val
                    conta.valor_recebido = conta.get_valor_total_com_ajustes()
                    conta.data_recebimento = lancamento_base.data
                    conta.status = 'pago'
                    conta.save()

                    # Criar baixa da conta a receber
                    from contasareceber.models import BaixaContaAReceber
                    baixa = BaixaContaAReceber.objects.create(
                        conta_a_receber=conta,
                        empresa_id=empresa_id,
                        data_recebimento=lancamento_base.data,
                        valor_recebido=conta.valor_recebido,
                        desconto=desconto_val,
                        juros=juros_val,
                        tarifas=tarifas_val,
                        conta_banco=lancamento_base.conta
                    )

                    # ExtratoMovimento: valor = líquido creditado neste título (soma dos movimentos
                    # do mesmo lançamento = valor do extrato, ex. 400 + 80 = 480).
                    nf_ref = ''
                    if conta.nota_id and conta.nota:
                        nf_ref = f"NF {conta.nota.numero_nota} "
                    descricao = (
                        f"{conta.valor_recebido:.2f} {nf_ref}{conta.doc or ''} {conta.cliente}".strip()
                    )
                    ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=lancamento_base.data,
                        descricao=descricao[:255],
                        valor=conta.valor_recebido,
                        situacao='recebido',
                        conta_banco=lancamento_base.conta,
                        lancamento=lancamento_base,
                        conta_receber=conta,
                        baixa_receber=baixa
                    )

                    # Atualizar status da nota fiscal
                    if conta.nota:
                        conta.nota.status_conciliacao = 'conciliado'
                        conta.nota.save()

                else:
                    # Processar contas a pagar
                    from contasapagar.models import ContasaPagar
                    conta = get_object_or_404(ContasaPagar, id=conta_id, empresa_id=empresa_id)

                    # Atualizar conta a pagar
                    conta.dtPag = lancamento_base.data
                    conta.valorPago = conta.valorDoc - desconto_val + juros_val + tarifas_val
                    conta.desconto = desconto_val
                    conta.juros = juros_val
                    conta.status = 'pago'
                    conta.save()

                    # Criar ExtratoMovimento
                    descricao = f"{conta.valorPago} {conta.numdoc or ''} {conta.fornecedor.razao if conta.fornecedor else ''}"
                    ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=lancamento_base.data,
                        descricao=descricao,
                        valor=conta.valorPago,
                        situacao='pago',
                        conta_banco=lancamento_base.conta,
                        lancamento=lancamento_base,
                        conta_pagar=conta
                    )

                    # Atualizar status da nota fiscal de entrada se existir
                    # (Aqui seria necessário verificar se há relação com notas fiscais de entrada)

            messages.success(request, f'Conciliação múltipla realizada com sucesso! {len(contas_selecionadas)} conta(s) processada(s).')
            # Preservar os filtros aplicados na URL de redirecionamento
            url = reverse('extrato:lancamento_list')
            query_params = request.GET.urlencode()
            if query_params:
                url += '?' + query_params
            return redirect(url)

    # GET - mostrar formulário
    context = {
        'lancamento_base': lancamento_base,
        'tipo_conta': request.GET.get('tipo_conta', 'receber'),
        'data_inicio': request.GET.get('data_inicio', ''),
        'data_fim': request.GET.get('data_fim', ''),
        'cliente_fornecedor': request.GET.get('cliente_fornecedor', ''),
        'title': f'Conciliar Múltiplo - {lancamento_base.historico}'
    }

    return render(request, 'extrato/conciliar_multiplo.html', context)


def _descricao_movimento_conciliacao_auto(regra, lancamento):
    """Texto para descrição de movimento; se definicao_historico pedir histórico do extrato, usa o do lançamento."""
    dh = (getattr(regra, "definicao_historico", None) or "")
    if "HISTORICO DO EXTRATO" in dh.upper():
        return lancamento.historico
    return dh or lancamento.historico or ""


@login_required
def conciliar_automatico_view(request):
    """
    View para conciliação automática baseada nas regras de conciliação
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:lista')

    # Aplicar os filtros da tela de listagem para buscar apenas lançamentos filtrados
    lancamentos_filtrados = aplicar_filtros_lancamento_list(Lancamento.objects.all(), request)

    if request.method == 'POST':
        ids = request.POST.getlist("lancamentos")  # lista de IDs selecionados na tela
        total_conciliados = 0

        with transaction.atomic():
            for lancamento_id in ids:
                lancamento = Lancamento.objects.get(id=lancamento_id, empresa_id=empresa_id)

                # Verificar se o lançamento está nos resultados filtrados atuais
                if not lancamentos_filtrados.filter(id=lancamento_id).exists():
                    messages.warning(request, f'Lançamento {lancamento_id} não está nos resultados filtrados atuais.')
                    continue

                # Verificar se já está conciliado
                if lancamento.conciliado:
                    continue

                # Buscar regras de conciliação da empresa
                from regraConciliacao.models import RegraConciliacao
                regras = RegraConciliacao.objects.filter(empresa_id=empresa_id)

                regra_encontrada = None
                for regra in regras:
                    # Verificar se a descrição da regra está contida no histórico do lançamento
                    if regra.descricao.lower() in lancamento.historico.lower():
                        regra_encontrada = regra
                        break

                if not regra_encontrada:
                    continue

                # Executar conciliação baseada na regra encontrada
                if regra_encontrada.tipo_conciliacao == 'transferencia':
                    # Para transferências, executar lógica similar ao botão Transferir
                    if not regra_encontrada.conta_bancaria_destino:
                        messages.error(request, f'Erro: Regra de conciliação {regra_encontrada.descricao} não tem conta bancária destino definida para o lançamento {lancamento_id}.')
                        continue

                    # Dados da transferência
                    conta_origem = lancamento.conta
                    conta_destino = regra_encontrada.conta_bancaria_destino
                    valor = lancamento.valor
                    data_transferencia = lancamento.data
                    descricao = f'Origem {conta_origem} para destino {conta_destino}'

                    # Criar 2 lançamentos no ExtratoMovimento conforme regras

                    # REF A CONTA DE ORIGEM - Usar o lançamento existente do extrato bancário
                    # Não criar novo lançamento, apenas o movimento
                    movimento_origem = ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=data_transferencia,
                        descricao=regra_encontrada.definicao_historico if regra_encontrada.definicao_historico else descricao,
                        valor=valor,  # Valor positivo do extrato
                        situacao='pago',  # Transferência de saída
                        conta_banco=conta_origem,
                        lancamento=lancamento,  # Vincular ao lançamento existente do extrato
                        categoria=None
                    )

                    # REF A CONTA DE DESTINO - Criar lançamento na tabela Lancamento
                    # Gerar um fitid único para evitar duplicatas
                    fitid_unico = f"TRANSF-{uuid.uuid4().hex[:8]}"
                    hash_unico = hashlib.sha256(
                        f"{fitid_unico}-{empresa_id}-{lancamento.id}-{data_transferencia}".encode()
                    ).hexdigest()

                    lancamento_destino = Lancamento.objects.create(
                        empresa_id=empresa_id,
                        data=data_transferencia,
                        valor=valor * -1,  # Valor negativo
                        historico=regra_encontrada.definicao_historico if regra_encontrada.definicao_historico else descricao,
                        documento='',
                        fitid=fitid_unico,  # FITID único para evitar duplicatas
                        hash_unico=hash_unico,
                        conta=conta_destino,
                        banco=conta_destino.banco,  # Adicionar banco
                        conciliado=True,
                        lancamento_origem_transferencia=lancamento  # Referência ao lançamento original
                    )

                    # REF A CONTA DE DESTINO - Movimento
                    movimento_destino = ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=data_transferencia,
                        descricao=regra_encontrada.definicao_historico if regra_encontrada.definicao_historico else descricao,
                        valor=valor * -1,  # Valor negativo
                        situacao='recebido',  # Transferência de entrada
                        conta_banco=conta_destino,
                        lancamento=lancamento_destino,  # Vincular ao novo lançamento
                        categoria=None
                    )

                    # Marcar o lançamento como conciliado
                    lancamento.conciliado = True
                    lancamento.save()

                elif lancamento.valor < 0:  # Valor negativo = despesa = contas a pagar
                    if not regra_encontrada.fornecedor:
                        messages.error(
                            request,
                            f'Erro: Regra "{regra_encontrada.descricao}" sem fornecedor para o lançamento {lancamento_id}.',
                        )
                        continue
                    if not regra_encontrada.categoria:
                        messages.error(
                            request,
                            f'Erro: Regra "{regra_encontrada.descricao}" sem categoria para o lançamento {lancamento_id}.',
                        )
                        continue
                    # Verificar se a regra tem forma de pagamento
                    if not regra_encontrada.forma_pagamento:
                        messages.error(request, f'Erro: Regra de conciliação {regra_encontrada.descricao} não tem forma de pagamento definida para o lançamento {lancamento_id}.')
                        continue

                    # Buscar uma cobrança compatível com a forma de pagamento
                    from cobranca.models import Cobranca
                    cobranca = Cobranca.objects.filter(descricao__icontains=regra_encontrada.forma_pagamento.descricao).first()
                    if not cobranca:
                        # Se não encontrar, pegar a primeira cobrança disponível
                        cobranca = Cobranca.objects.first()
                        if not cobranca:
                            messages.error(request, f'Erro: Nenhuma cobrança encontrada no sistema para o lançamento {lancamento_id}.')
                            continue

                    # Criar conta a pagar
                    conta_pagar = ContasaPagar.objects.create(
                        empresa_id=empresa_id,
                        dtEmissao=lancamento.data,
                        dtPag=lancamento.data,
                        dtvenc=lancamento.data,
                        fornecedor=regra_encontrada.fornecedor,
                        descricao=_descricao_movimento_conciliacao_auto(regra_encontrada, lancamento)[:100],
                        numdoc='0',
                        valorDoc=abs(lancamento.valor),
                        valorPago=abs(lancamento.valor),
                        categoria=regra_encontrada.categoria,
                        cobranca=regra_encontrada.forma_pagamento or cobranca,
                        parcela='1',
                        desconto=0,
                        juros=0,
                        multa=0,
                        status='pago',
                        conta_banco=lancamento.conta,
                        obs=f'Conciliado automaticamente - Regra: {regra_encontrada.descricao}',
                        nossonumero='',
                        nsu='',
                    )

                    # Criar ExtratoMovimento
                    ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=lancamento.data,
                        descricao=_descricao_movimento_conciliacao_auto(regra_encontrada, lancamento)[:255],
                        situacao='pago',
                        valor=lancamento.valor,  # Manter sinal original
                        conta_pagar=conta_pagar,
                        lancamento=lancamento,
                        conta_banco=lancamento.conta,
                        categoria=regra_encontrada.categoria
                    )

                else:  # Valor positivo = receita = contas a receber
                    # Criar conta a receber (cliente no modelo é CharField: usar razão do cadastro ou histórico)
                    from contasareceber.models import ContaAReceber
                    cli = regra_encontrada.cliente
                    if cli:
                        cliente_nome = (cli.razao or "")[:200]
                        cnpj_cli = (cli.cnpj or "")[:18]
                    else:
                        cliente_nome = (lancamento.historico or "Cliente")[:200]
                        cnpj_cli = ""
                    conta_receber = ContaAReceber.objects.create(
                        empresa_id=empresa_id,
                        cliente=cliente_nome,
                        cnpj_cpf=cnpj_cli or None,
                        categoria=regra_encontrada.categoria,
                        doc='',
                        data_emissao=lancamento.data,
                        data_vencimento=lancamento.data,
                        data_recebimento=lancamento.data,
                        forma_pagamento=regra_encontrada.forma_pagamento,
                        valor_a_receber=lancamento.valor,
                        valor_recebido=lancamento.valor,
                        desconto=0,
                        juros=0,
                        tarifas=0,
                        status='pago',
                        observacao=f'Conciliado automaticamente - Regra: {regra_encontrada.descricao}',
                        conta_banco=lancamento.conta,
                    )

                    # Criar baixa da conta a receber
                    from contasareceber.models import BaixaContaAReceber
                    baixa = BaixaContaAReceber.objects.create(
                        conta_a_receber=conta_receber,
                        empresa_id=empresa_id,
                        valor_recebido=lancamento.valor,
                        data_recebimento=lancamento.data,
                        conta_banco=lancamento.conta
                    )

                    # Criar ExtratoMovimento
                    ExtratoMovimento.objects.create(
                        empresa_id=empresa_id,
                        data_baixa=lancamento.data,
                        descricao=_descricao_movimento_conciliacao_auto(regra_encontrada, lancamento)[:255],
                        situacao='recebido',
                        valor=lancamento.valor,
                        conta_receber=conta_receber,
                        baixa_receber=baixa,
                        lancamento=lancamento,
                        conta_banco=lancamento.conta,
                        categoria=regra_encontrada.categoria
                    )

                # Marcar lançamento como conciliado
                lancamento.conciliado = True
                lancamento.save()
                total_conciliados += 1

        messages.success(request, f'Conciliação automática concluída! {total_conciliados} lançamento(s) conciliado(s).')
        return redirect("extrato:lancamento_list")

    # GET - redirecionar para lista
    return redirect("extrato:lancamento_list")


@login_required
def sicoob_baixar_extrato_view(request):
    """
    Baixa extrato mensal via API Conta Corrente Sicoob (v4) e grava lançamentos (origem SICOOB_API).
    Requer SICOOB_CLIENT_ID e, em produção, certificado mTLS (SICOOB_MTLS_CERT / SICOOB_MTLS_KEY).
    """
    empresa_id = request.session.get("empresa_id")
    if not empresa_id:
        messages.error(request, "Selecione uma empresa para continuar.")
        return redirect("empresa:lista")
    if request.method != "POST":
        messages.warning(request, "Use o formulário na tela de extrato.")
        return redirect("extrato:lancamento_list")

    from .services.sicoob_api import consultar_extrato_sicoob
    from .services.sicoob_importer import conta_numero_api_sicoob, importar_extrato_sicoob_json

    try:
        conta_id = int(request.POST.get("conta_id") or "0")
    except ValueError:
        conta_id = 0
    if not conta_id:
        messages.error(request, "Selecione a conta Sicoob.")
        return redirect("extrato:lancamento_list")

    try:
        mes = int(request.POST.get("mes") or "0")
        ano = int(request.POST.get("ano") or "0")
    except ValueError:
        mes, ano = 0, 0
    if mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
        messages.error(request, "Informe mês (1–12) e ano válidos.")
        return redirect("extrato:lancamento_list")

    dia_ini = request.POST.get("dia_inicial") or ""
    dia_fim = request.POST.get("dia_final") or ""
    d1 = int(dia_ini) if dia_ini.isdigit() else None
    d2 = int(dia_fim) if dia_fim.isdigit() else None

    conta = (
        ContaBancaria.objects.filter(pk=conta_id, empresa_id=empresa_id)
        .select_related("banco")
        .first()
    )
    if not conta:
        messages.error(request, "Conta não encontrada.")
        return redirect("extrato:lancamento_list")

    cod_raw = (conta.banco.codigo or "").strip()
    cod_norm = cod_raw.lstrip("0") or cod_raw
    nome_b = (conta.banco.nome or "").lower()
    if cod_norm not in ("756", "306") and "sicoob" not in nome_b:
        messages.error(request, "A conta selecionada não é Sicoob (código 756/306).")
        return redirect("extrato:lancamento_list")

    try:
        ncc = conta_numero_api_sicoob(conta)
        payload = consultar_extrato_sicoob(
            mes, ano, ncc, dia_inicial=d1, dia_final=d2, empresa=conta.empresa
        )
        criados, ignorados = importar_extrato_sicoob_json(conta, payload)
    except Exception as e:
        logger.exception("sicoob_baixar_extrato")
        messages.error(request, str(e))
        return redirect("extrato:lancamento_list")

    messages.success(
        request,
        f"Extrato Sicoob importado: {criados} lançamento(s) criado(s), {ignorados} ignorado(s) ou duplicado(s).",
    )
    return redirect("extrato:lancamento_list")


@login_required
def conciliar_despesa_view(request):
    """View para conciliar despesa baseada em lançamento do extrato bancário"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa para continuar.')
        return redirect('empresa:lista')

    # Aplicar os filtros da tela de listagem para verificar se o lançamento está nos resultados filtrados
    lancamentos_filtrados = aplicar_filtros_lancamento_list(Lancamento.objects.all(), request)

    # Função auxiliar para criar URL com filtros preservados
    def redirect_com_filtros():
        """Redireciona para a lista mantendo os filtros aplicados"""
        from django.urls import reverse
        url = reverse('extrato:lancamento_list')
        query_params = request.GET.urlencode()
        if query_params:
            url += '?' + query_params
        return redirect(url)

    if request.method == 'POST':
        lancamento_id = request.POST.get('lancamento_id')
        categoria_id = request.POST.get('categoria_id')
        forma_pagamento_id = request.POST.get('forma_pagamento_id')
        numero_nota = request.POST.get('numero_nota')
        data_emissao = request.POST.get('data_emissao')
        fornecedor_id = request.POST.get('fornecedor_id')

        try:
            with transaction.atomic():
                # Buscar lançamento
                lancamento = Lancamento.objects.get(id=lancamento_id, empresa_id=empresa_id)

                # Verificar se o lançamento está nos resultados filtrados atuais
                if not lancamentos_filtrados.filter(id=lancamento_id).exists():
                    messages.warning(request, 'O lançamento selecionado não está nos resultados filtrados atuais.')
                    return redirect_com_filtros()

                # Verificar se já está conciliado
                if lancamento.conciliado:
                    messages.error(request, 'Este lançamento já está conciliado.')
                    return redirect_com_filtros()

                # Verificar se é valor negativo (despesa)
                if lancamento.valor >= 0:
                    messages.error(request, 'Esta funcionalidade é apenas para lançamentos de despesa (valores negativos).')
                    return redirect_com_filtros()

                # Buscar objetos relacionados
                categoria = Categoria.objects.get(id=categoria_id, empresa_id=empresa_id)
                forma_pagamento = Cobranca.objects.get(id=forma_pagamento_id)
                fornecedor = None
                if fornecedor_id:
                    fornecedor = Fornecedor.objects.get(id=fornecedor_id)

                # Buscar uma cobrança compatível com a forma de pagamento
                from cobranca.models import Cobranca
                cobranca = Cobranca.objects.filter(descricao__icontains=forma_pagamento.descricao).first()
                if not cobranca:
                    # Se não encontrar, pegar a primeira cobrança disponível
                    cobranca = Cobranca.objects.first()
                if not cobranca:
                    raise ValueError("Nenhuma cobrança encontrada no sistema")

                # Definir data de emissão
                if not data_emissao:
                    data_emissao = lancamento.data
                else:
                    data_emissao = datetime.strptime(data_emissao, '%Y-%m-%d').date()

                # Criar conta a pagar
                conta_pagar = ContasaPagar.objects.create(
                    dtEmissao=data_emissao,
                    fornecedor=fornecedor,
                    descricao=lancamento.historico,
                    numdoc=numero_nota or '',
                    valorDoc=abs(lancamento.valor),  # Valor positivo
                    categoria=categoria,
                    parcela='1',
                    desconto=0,
                    dtvenc=lancamento.data,
                    dtPag=lancamento.data,
                    juros=0,
                    multa=0,
                    valorPago=abs(lancamento.valor),  # Valor positivo
                    cobranca=forma_pagamento or cobranca,
                    conta_banco=lancamento.conta,
                    obs=f'Conciliado automaticamente - Lançamento {lancamento.id}',
                    nossonumero='',
                    nsu='',
                    status='pago',
                )

                # Marcar lançamento como conciliado
                lancamento.conciliado = True
                lancamento.save()

                # Criar ExtratoMovimento
                nome_fornecedor = fornecedor.razao if fornecedor else ''
                descricao_movimento = f"{lancamento.historico} - {numero_nota or ''} {nome_fornecedor}".strip()

                ExtratoMovimento.objects.create(
                    empresa_id=empresa_id,
                    data_baixa=lancamento.data,
                    descricao=descricao_movimento,
                    situacao='pago',
                    valor=lancamento.valor,  # Manter o sinal original (negativo para despesas)
                    conta_pagar=conta_pagar,
                    lancamento=lancamento,
                    conta_banco=lancamento.conta,
                    categoria=categoria
                )

                messages.success(request, f'Despesa conciliada com sucesso! Conta a pagar criada: {conta_pagar.descricao}')
                return redirect_com_filtros()

        except Exception as e:
            messages.error(request, f'Erro ao conciliar despesa: {str(e)}')
            return redirect_com_filtros()

    # GET - redirecionar para lista
    return redirect_com_filtros()
