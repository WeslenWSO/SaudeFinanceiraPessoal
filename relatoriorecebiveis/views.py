from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Sum
import csv
import io
import re
import unicodedata
from datetime import datetime, date, timedelta
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from .models import RelatorioRecebiveisMaquinaCartao
from .forms import RelatorioRecebiveisForm, CSVImportForm, InfinitePayPDFImportForm, CieloXLSXImportForm
from .infinitepay_pdf import parse_infinitepay_pdf_bytes, _normalize_parcela_display
from .infinitepay_gemini import parse_infinitepay_pdf_with_gemini, validate_gemini_api_key
from .cielo_xlsx import parse_cielo_xlsx_bytes
from .stone_csv import parse_stone_csv_bytes
from empresa.models import Empresa, UsuarioEmpresa
from extrato.models import Lancamento


def normalize_text(text):
    """Normaliza texto: converte para minúsculo e remove acentos"""
    if not text:
        return ''
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')


def _parse_currency_value(value_str):
    """Função utilitária para processar valores monetários de diferentes formatos"""
    if not value_str or not value_str.strip():
        return None

    # Remove tudo exceto números, ponto e vírgula
    cleaned_value = re.sub(r'[^\d.,]', '', value_str.strip())

    # Substitui vírgula por ponto
    cleaned_value = cleaned_value.replace(',', '.')

    # Trata casos com múltiplos pontos (separadores de milhares)
    if cleaned_value.count('.') > 1:
        partes = cleaned_value.split('.')
        cleaned_value = ''.join(partes[:-1]) + '.' + partes[-1]

    try:
        return float(cleaned_value)
    except ValueError:
        return None

@login_required
def relatorio_recebiveis_list(request):
    """Lista todos os relatórios de recebíveis com filtros"""
    # Obter empresa do usuário da sessão (empresa atualmente selecionada)
    try:
        empresa_id = request.session.get('empresa_id')
        if empresa_id:
            empresa = Empresa.objects.get(id=empresa_id)
            relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(empresa=empresa)
        else:
            # Fallback: tenta encontrar empresa ativa do usuário
            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
            if not usuario_empresa:
                # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                if not usuario_empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('accounts:login')
            empresa = usuario_empresa.empresa
            relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(empresa=empresa)
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa selecionada não encontrada.')
        return redirect('accounts:login')
    except Exception as e:
        messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
        return redirect('accounts:login')

    # Filtros
    periodo = request.GET.get('periodo', 'todos')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')

    # Lógica de navegação por meses com estado
    hoje = date.today()
    mes_atual_visualizacao = request.session.get('relatorios_recebiveis_mes_atual', hoje.year * 12 + hoje.month)

    # Converter de volta para ano e mês
    ano_atual = mes_atual_visualizacao // 12
    mes_atual = mes_atual_visualizacao % 12
    if mes_atual == 0:
        ano_atual -= 1
        mes_atual = 12

    # Calcular limite (12 meses para trás)
    mes_limite = hoje.year * 12 + hoje.month - 12

    if periodo:
        if periodo == 'mes_atual':
            # Reset para mês atual
            mes_atual_visualizacao = hoje.year * 12 + hoje.month
            request.session['relatorios_recebiveis_mes_atual'] = mes_atual_visualizacao
            ano_atual = hoje.year
            mes_atual = hoje.month
        elif periodo == 'mes_anterior':
            # Decrementar mês (navegar para trás)
            if mes_atual_visualizacao > mes_limite:
                mes_atual_visualizacao -= 1
                request.session['relatorios_recebiveis_mes_atual'] = mes_atual_visualizacao

                # Recalcular ano e mês
                ano_atual = mes_atual_visualizacao // 12
                mes_atual = mes_atual_visualizacao % 12
                if mes_atual == 0:
                    ano_atual -= 1
                    mes_atual = 12

    # Aplicar filtro do mês atual sendo visualizado
    if periodo in ['mes_atual', 'mes_anterior'] or not periodo:
        # Primeiro e último dia do mês sendo visualizado
        primeiro_dia_mes = date(ano_atual, mes_atual, 1)
        ultimo_dia_mes = date(ano_atual, mes_atual, monthrange(ano_atual, mes_atual)[1])
        relatorios = relatorios.filter(data_pagamento__range=(primeiro_dia_mes, ultimo_dia_mes))
    elif periodo == 'personalizado' and data_inicio and data_fim:
        try:
            # Tentar múltiplos formatos de data conforme definido em settings.py
            data_inicio_parsed = None
            data_fim_parsed = None

            for fmt in ['%Y-%m-%d', '%d/%m/%Y']:
                try:
                    if not data_inicio_parsed:
                        data_inicio_parsed = datetime.strptime(data_inicio, fmt).date()
                    if not data_fim_parsed:
                        data_fim_parsed = datetime.strptime(data_fim, fmt).date()
                    if data_inicio_parsed and data_fim_parsed:
                        break
                except ValueError:
                    continue

            if data_inicio_parsed and data_fim_parsed:
                relatorios = relatorios.filter(data_pagamento__gte=data_inicio_parsed, data_pagamento__lte=data_fim_parsed)
        except Exception:
            pass  # Ignorar se datas inválidas

    # Filtro por máquina (maquininha)
    maquina_filtro = request.GET.getlist('maquina')
    if maquina_filtro:
        relatorios = relatorios.filter(maquinha__in=maquina_filtro)

    # Filtro por bandeira
    bandeira_filtro = request.GET.getlist('bandeira')
    if bandeira_filtro:
        relatorios = relatorios.filter(bandeira__in=bandeira_filtro)

    # Filtro por forma de pagamento
    forma_pagamento_filtro = request.GET.getlist('forma_pagamento')
    if forma_pagamento_filtro:
        relatorios = relatorios.filter(forma_pagamento__in=forma_pagamento_filtro)

    relatorios = relatorios.order_by('-data_pagamento')

    # Máquinas distintas para filtro
    maquinas_labels = dict(RelatorioRecebiveisMaquinaCartao.MAQUINHA_CHOICES)
    maquinas_raw = (
        RelatorioRecebiveisMaquinaCartao.objects.filter(empresa=empresa)
        .exclude(maquinha__isnull=True)
        .exclude(maquinha='')
        .values_list('maquinha', flat=True)
        .distinct()
    )
    maquinas_distinct = sorted(
        [(m, maquinas_labels.get(m, m)) for m in set(maquinas_raw)],
        key=lambda x: x[1],
    )

    # Bandeiras distintas para filtro (case insensitive unique)
    bandeiras_raw = relatorios.values_list('bandeira', flat=True).distinct().exclude(bandeira__isnull=True).exclude(bandeira='')
    bandeiras_dict = {}
    for b in bandeiras_raw:
        key = b.lower()
        if key not in bandeiras_dict:
            bandeiras_dict[key] = b
    bandeiras_distinct = list(bandeiras_dict.values())

    # Formas de pagamento distintas para filtro (case insensitive unique)
    formas_raw = relatorios.values_list('forma_pagamento', flat=True).distinct().exclude(forma_pagamento__isnull=True).exclude(forma_pagamento='')
    formas_dict = {}
    for f in formas_raw:
        key = f.lower()
        if key not in formas_dict:
            formas_dict[key] = f
    formas_distinct = list(formas_dict.values())

    # Totais gerais
    totals = relatorios.aggregate(
        total_bruto=Sum('valor_bruto'),
        total_taxa=Sum('taxa_maquinha'),
        total_liquido=Sum('valor_liquido')
    )

    # Totais por bandeira
    bandeira_totals = relatorios.values('bandeira').annotate(
        total_bruto=Sum('valor_bruto'),
        total_taxa=Sum('taxa_maquinha'),
        total_liquido=Sum('valor_liquido')
    ).exclude(bandeira__isnull=True).exclude(bandeira='').order_by('bandeira')

    # Determinar o texto do período selecionado
    periodo_texto = ''
    if periodo in ['mes_atual', 'mes_anterior'] or not periodo:
        import calendar
        nome_mes = calendar.month_name[mes_atual]
        periodo_texto = f"{nome_mes} {ano_atual}"

    # Determinar se pode navegar para trás
    pode_navegar_anterior = mes_atual_visualizacao > mes_limite

    # IDs de cobrança para link Data Venda → Contas a Receber
    from cobranca.models import Cobranca

    def _id_cobranca_cartao(tipo: str):
        """tipo: 'debito' | 'credito' — retorna id da Cobranca correspondente."""
        qs = Cobranca.objects.all()
        for c in qs:
            d = unicodedata.normalize('NFKD', c.descricao or '')
            d = ''.join(ch for ch in d if not unicodedata.combining(ch)).upper().replace(' ', '')
            if tipo == 'debito' and ('DEBITO' in d or 'DEBIT' in d) and 'CREDITO' not in d:
                return c.id
            if tipo == 'credito' and ('CREDITO' in d or 'CREDIT' in d):
                return c.id
        return None

    cobranca_cartao_debito_id = _id_cobranca_cartao('debito')
    cobranca_cartao_credito_id = _id_cobranca_cartao('credito')

    return render(request, 'relatoriorecebiveis/list.html', {
        'relatorios': relatorios,
        'title': 'Relatórios de Recebíveis - Máquina de Cartão',
        'periodo': periodo,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'maquina_filtro': maquina_filtro,
        'maquinas_distinct': maquinas_distinct,
        'bandeira_filtro': bandeira_filtro,
        'bandeiras_distinct': bandeiras_distinct,
        'forma_pagamento_filtro': forma_pagamento_filtro,
        'formas_distinct': formas_distinct,
        'totals': totals,
        'bandeira_totals': bandeira_totals,
        'periodo_texto': periodo_texto,
        'pode_navegar_anterior': pode_navegar_anterior,
        'cobranca_cartao_debito_id': cobranca_cartao_debito_id,
        'cobranca_cartao_credito_id': cobranca_cartao_credito_id,
    })

def relatorio_recebiveis_detail(request, pk):
    """Visualiza detalhes de um relatório específico"""
    # Obter empresa do usuário da sessão
    try:
        empresa_id = request.session.get('empresa_id')
        if empresa_id:
            empresa = Empresa.objects.get(id=empresa_id)
        else:
            # Fallback: tenta encontrar empresa ativa do usuário
            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
            if not usuario_empresa:
                # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                if not usuario_empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('accounts:login')
            empresa = usuario_empresa.empresa
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa selecionada não encontrada.')
        return redirect('accounts:login')
    except Exception as e:
        messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
        return redirect('accounts:login')

    relatorio = get_object_or_404(RelatorioRecebiveisMaquinaCartao, pk=pk, empresa=empresa)
    return render(request, 'relatoriorecebiveis/detail.html', {
        'relatorio': relatorio,
        'title': f'Relatório #{relatorio.id}'
    })

def relatorio_recebiveis_create(request):
    """Cria um novo relatório de recebíveis"""
    # Obter empresa do usuário da sessão
    try:
        empresa_id = request.session.get('empresa_id')
        if empresa_id:
            empresa = Empresa.objects.get(id=empresa_id)
        else:
            # Fallback: tenta encontrar empresa ativa do usuário
            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
            if not usuario_empresa:
                # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                if not usuario_empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('accounts:login')
            empresa = usuario_empresa.empresa
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa selecionada não encontrada.')
        return redirect('accounts:login')
    except Exception as e:
        messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
        return redirect('accounts:login')

    if request.method == 'POST':
        form = RelatorioRecebiveisForm(request.POST)
        if form.is_valid():
            relatorio = form.save(commit=False)
            relatorio.empresa = empresa
            relatorio.save()
            messages.success(request, 'Relatório criado com sucesso!')
            return redirect('relatoriorecebiveis:detail', pk=relatorio.pk)
    else:
        form = RelatorioRecebiveisForm()

    return render(request, 'relatoriorecebiveis/form.html', {
        'form': form,
        'title': 'Novo Relatório de Recebíveis',
        'action': 'Criar'
    })

def relatorio_recebiveis_update(request, pk):
    """Atualiza um relatório existente"""
    # Obter empresa do usuário da sessão
    try:
        empresa_id = request.session.get('empresa_id')
        if empresa_id:
            empresa = Empresa.objects.get(id=empresa_id)
        else:
            # Fallback: tenta encontrar empresa ativa do usuário
            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
            if not usuario_empresa:
                # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                if not usuario_empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('accounts:login')
            empresa = usuario_empresa.empresa
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa selecionada não encontrada.')
        return redirect('accounts:login')
    except Exception as e:
        messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
        return redirect('accounts:login')

    relatorio = get_object_or_404(RelatorioRecebiveisMaquinaCartao, pk=pk, empresa=empresa)

    if relatorio.conciliado:
        messages.warning(request, 'Relatórios já conciliados não podem ser editados.')
        return redirect('relatoriorecebiveis:detail', pk=relatorio.pk)

    if request.method == 'POST':
        form = RelatorioRecebiveisForm(request.POST, instance=relatorio)
        if form.is_valid():
            relatorio = form.save()
            messages.success(request, 'Relatório atualizado com sucesso!')
            return redirect('relatoriorecebiveis:detail', pk=relatorio.pk)
    else:
        form = RelatorioRecebiveisForm(instance=relatorio)

    return render(request, 'relatoriorecebiveis/form.html', {
        'form': form,
        'relatorio': relatorio,
        'title': f'Editar Relatório #{relatorio.id}',
        'action': 'Atualizar'
    })

def relatorio_recebiveis_delete(request, pk):
    """Remove um relatório"""
    # Obter empresa do usuário da sessão
    try:
        empresa_id = request.session.get('empresa_id')
        if empresa_id:
            empresa = Empresa.objects.get(id=empresa_id)
        else:
            # Fallback: tenta encontrar empresa ativa do usuário
            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
            if not usuario_empresa:
                # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                if not usuario_empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('accounts:login')
            empresa = usuario_empresa.empresa
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa selecionada não encontrada.')
        return redirect('accounts:login')
    except Exception as e:
        messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
        return redirect('accounts:login')

    relatorio = get_object_or_404(RelatorioRecebiveisMaquinaCartao, pk=pk, empresa=empresa)

    if relatorio.conciliado:
        messages.warning(request, 'Relatórios já conciliados não podem ser excluídos.')
        return redirect('relatoriorecebiveis:detail', pk=relatorio.pk)

    if request.method == 'POST':
        relatorio.delete()
        messages.success(request, 'Relatório removido com sucesso!')
        return redirect('relatoriorecebiveis:relReclist')

    return render(request, 'relatoriorecebiveis/delete.html', {
        'relatorio': relatorio,
        'title': f'Remover Relatório #{relatorio.id}'
    })


def _empresa_recebiveis_request(request):
    """Retorna empresa da sessão ou None."""
    try:
        empresa_id = request.session.get('empresa_id')
        if empresa_id:
            return Empresa.objects.get(id=empresa_id)
        usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
        if not usuario_empresa:
            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
        return usuario_empresa.empresa if usuario_empresa else None
    except Empresa.DoesNotExist:
        return None


@login_required
def relatorio_recebiveis_delete_bulk(request):
    """Remove vários relatórios não conciliados selecionados na listagem."""
    if request.method != 'POST':
        return redirect('relatoriorecebiveis:relReclist')

    empresa = _empresa_recebiveis_request(request)
    if not empresa:
        messages.error(request, 'Empresa não selecionada.')
        return redirect('relatoriorecebiveis:relReclist')

    raw_ids = request.POST.getlist('selected_ids')
    if not raw_ids:
        messages.warning(request, 'Nenhum recebível selecionado para exclusão.')
        return redirect(request.META.get('HTTP_REFERER') or reverse('relatoriorecebiveis:relReclist'))

    try:
        ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        messages.error(request, 'Seleção inválida.')
        return redirect(request.META.get('HTTP_REFERER') or reverse('relatoriorecebiveis:relReclist'))

    selecionados = RelatorioRecebiveisMaquinaCartao.objects.filter(pk__in=ids, empresa=empresa)
    conciliados = selecionados.filter(conciliado=True).count()
    excluir_qs = selecionados.filter(conciliado=False)

    with transaction.atomic():
        excluidos, _ = excluir_qs.delete()

    if excluidos:
        messages.success(request, f'{excluidos} recebível(is) excluído(s) com sucesso.')
    else:
        messages.warning(request, 'Nenhum recebível pôde ser excluído.')
    if conciliados:
        messages.warning(
            request,
            f'{conciliados} recebível(is) conciliado(s) foram ignorados (desconcilie antes de excluir).',
        )

    return redirect(request.META.get('HTTP_REFERER') or reverse('relatoriorecebiveis:relReclist'))


@login_required
def relatorio_recebiveis_import_csv(request):
    """Importa relatórios de recebíveis via arquivo CSV"""
    if request.method == 'POST':
        # Verificar se é confirmação de importação
        if 'confirm_import' in request.POST:
            return _process_csv_import(request)

        form = CSVImportForm(request.POST, request.FILES)

        if form.is_valid():

            csv_file = form.cleaned_data['csv_file']
            selected_maquina = form.cleaned_data['maquinha']

            if csv_file.size == 0:
                messages.error(request, 'O arquivo selecionado está vazio.')
                return redirect('relatoriorecebiveis:import_csv')

            # Verificar extensão
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'O arquivo deve ter extensão .csv')
                return redirect('relatoriorecebiveis:import_csv')

            # Processar arquivo para prévia
            try:
                file_bytes = csv_file.read()

                # Obter empresa do usuário da sessão (empresa atualmente selecionada)
                try:
                    empresa_id = request.session.get('empresa_id')
                    if empresa_id:
                        empresa = Empresa.objects.get(id=empresa_id)
                    else:
                        # Fallback: tenta encontrar empresa ativa do usuário
                        usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
                        if not usuario_empresa:
                            # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                            usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                            if not usuario_empresa:
                                messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                                return redirect('relatoriorecebiveis:relReclist')
                        empresa = usuario_empresa.empresa
                except Empresa.DoesNotExist:
                    messages.error(request, 'Empresa selecionada não encontrada.')
                    return redirect('relatoriorecebiveis:relReclist')
                except Exception as e:
                    messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
                    return redirect('relatoriorecebiveis:relReclist')

                # Layout Stone (CSV de recebimentos do portal)
                if selected_maquina == 'STONE':
                    rows, parse_warnings = parse_stone_csv_bytes(file_bytes)
                    preview_data = []
                    errors = list(parse_warnings)
                    for row in rows:
                        preview_data.append({
                            'linha': row.get('linha'),
                            'data_pagamento': row.get('data_pagamento'),
                            'forma_pagamento': row.get('forma_pagamento'),
                            'bandeira': row.get('bandeira'),
                            'valor_bruto': row.get('valor_bruto'),
                            'taxa_maquinha': row.get('taxa_maquinha'),
                            'valor_liquido': row.get('valor_liquido'),
                            'maquinha': 'STONE',
                            'numero_autorizacao': row.get('numero_autorizacao'),
                            'data_venda': row.get('data_venda'),
                            'nsu_doc': row.get('nsu_doc'),
                            'parcelas': row.get('parcela_texto') or row.get('parcelas'),
                            'total_parcelas': row.get('total_parcelas'),
                            'conciliado': row.get('conciliado') or 'Não',
                            'nota_fiscal': row.get('nota_fiscal'),
                            'razao': row.get('razao'),
                        })
                    if not preview_data:
                        for w in parse_warnings[:8]:
                            messages.warning(request, w)
                        messages.error(request, 'Nenhum recebimento Stone válido encontrado no arquivo.')
                        return redirect('relatoriorecebiveis:import_csv')

                    request.session['csv_preview_data'] = {
                        'filename': csv_file.name,
                        'content': '',
                        'rows': rows,
                        'empresa_id': empresa.id,
                        'total_rows': len(preview_data),
                        'valid_rows': len(preview_data),
                        'invalid_rows': len(parse_warnings),
                        'selected_maquina': 'STONE',
                    }
                    request.session.modified = True
                    return render(request, 'relatoriorecebiveis/import_csv_preview.html', {
                        'title': 'Prévia da Importação CSV — Stone',
                        'preview_data': preview_data,
                        'errors': errors,
                        'filename': csv_file.name,
                        'empresa': empresa,
                        'selected_maquina': 'STONE',
                        'total_rows': len(preview_data),
                        'valid_rows': len(preview_data),
                        'invalid_rows': len(parse_warnings),
                        'confirm_import_url': reverse('relatoriorecebiveis:import_csv'),
                        'back_upload_url': reverse('relatoriorecebiveis:import_csv'),
                    })

                decoded_file = file_bytes.decode('utf-8-sig')
                io_string = io.StringIO(decoded_file)
                reader = csv.DictReader(io_string, delimiter=';')

                # Processar linhas para prévia
                preview_data = []
                total_rows = 0
                valid_rows = 0
                invalid_rows = 0
                errors = []

                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Tentar múltiplas variações do campo de data de pagamento
                        data_pagamento = None
                        data_field_names = [
                            'Data de pagamento',  # Com acento
                            'Data do pagamento',  # Com acento
                            'Data de Pagamento',  # Com acento maiúsculo
                            'Data do Pagamento',  # Com acento maiúsculo
                            'data de pagamento',  # Minúsculo
                            'data do pagamento',  # Minúsculo
                            'Data_pagamento',     # Com underscore
                            'Data_pagamento',     # Com underscore
                        ]

                        for field_name in data_field_names:
                            if field_name in row and row[field_name].strip():
                                data_pagamento = row[field_name].strip()
                                break

                        # Verificar se data de pagamento está presente
                        if not data_pagamento:
                            errors.append(f"Linha {row_num}: Data de pagamento ausente - registro será ignorado na importação")
                            invalid_rows += 1
                            continue

                        # Tentar validar formato da data
                        data_valida = False
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                datetime.strptime(data_pagamento, fmt).date()
                                data_valida = True
                                break
                            except ValueError:
                                continue

                        if not data_valida:
                            errors.append(f"Linha {row_num}: Formato de data inválido '{data_pagamento}' - registro será ignorado na importação")
                            invalid_rows += 1
                            continue

                        # Validar e formatar dados para prévia
                        if selected_maquina == 'CIELO':
                            # Mapeamento específico para CIELO na prévia
                            forma_pagamento = row.get('Forma de pagamento', '').strip()
                            bandeira = row.get('Bandeira', '').strip()
                            valor_bruto = row.get('Valor bruto', '').strip()
                            taxa_maquinha = row.get('Valor Taxa', '').strip()
                            valor_liquido = row.get('Valor liquido', '').strip()
                            numero_autorizacao = row.get('N. Autorizacao', '').strip()
                            data_venda = row.get('Data da venda', '').strip()
                            nsu_doc = row.get('NSU/DOC', '').strip()

                            # Lógica para parcelas
                            forma_pagamento_lower = forma_pagamento.lower() if forma_pagamento else ''
                            is_debito = 'debito' in forma_pagamento_lower or 'débito' in forma_pagamento_lower

                            if is_debito:
                                parcelas = '1'
                                total_parcelas = '1'
                            else:
                                parcelas = row.get('Número da parcela', '1').strip()
                                total_parcelas = row.get('Quantidade total de parcelas', '1').strip()

                            preview_row = {
                                'linha': row_num - 1,
                                'data_pagamento': data_pagamento,
                                'forma_pagamento': forma_pagamento,
                                'bandeira': bandeira,
                                'valor_bruto': valor_bruto,
                                'taxa_maquinha': taxa_maquinha,
                                'valor_liquido': valor_liquido,
                                'maquinha': 'CIELO',
                                'numero_autorizacao': numero_autorizacao,
                                'data_venda': data_venda,
                                'nsu_doc': nsu_doc,
                                'parcelas': parcelas,
                                'total_parcelas': total_parcelas,
                                'conciliado': row.get('Conciliado', '').strip(),
                                'nota_fiscal': row.get('Nota Fiscal', '').strip(),
                                'razao': row.get('Razão', '').strip(),
                            }
                        elif selected_maquina == 'INFINTY':
                            # Mapeamento específico para INFINTY na prévia
                            forma_pagamento = row.get('Forma Pagamento', '').strip()
                            bandeira = row.get('Bandeira', '').strip()
                            valor_bruto = row.get('Valor Bruto', '').strip()
                            # Tentar variações do campo Taxa (Valor Taxa ou Taxa Máquina)
                            taxa_maquinha = (
                                row.get('Valor Taxa', '').strip() or
                                row.get('Taxa Máquina', '').strip()
                            )
                            # Tentar variações do campo Valor Líquido (com e sem acento)
                            valor_liquido = (
                                row.get('Valor Líquido', '').strip() or
                                row.get('Valor Liquido', '').strip()
                            )
                            # Tentar variações do campo Autorização
                            numero_autorizacao = (
                                row.get('Autorização', '').strip() or
                                row.get('N° Autorização', '').strip() or
                                row.get('Autorizacao', '').strip()
                            )
                            data_venda = row.get('Data Venda', '').strip()
                            # Tentar variações do campo Parcelas
                            parcelas = (
                                row.get('Parcelas', '').strip() or
                                row.get('Número da parcela', '').strip() or
                                row.get('Parcela', '').strip() or
                                '1'
                            )
                            # Tentar variações do campo Total de Parcelas
                            total_parcelas = (
                                row.get('Total de Parcelas', '').strip() or
                                row.get('Quantidade total de parcelas', '').strip() or
                                row.get('Total de parcela', '').strip() or
                                parcelas  # Mesmo valor se não encontrar
                            )

                            preview_row = {
                                'linha': row_num - 1,
                                'data_pagamento': data_pagamento,
                                'forma_pagamento': forma_pagamento,
                                'bandeira': bandeira,
                                'valor_bruto': valor_bruto,
                                'taxa_maquinha': taxa_maquinha,
                                'valor_liquido': valor_liquido,
                                'maquinha': 'INFINTY',
                                'numero_autorizacao': numero_autorizacao,
                                'data_venda': data_venda,
                                'nsu_doc': numero_autorizacao,  # Usar autorização como NSU/DOC
                                'parcelas': parcelas,
                                'total_parcelas': total_parcelas,
                                'conciliado': row.get('Conciliado', '').strip(),
                                'nota_fiscal': row.get('Nota Fiscal', '').strip(),
                                'razao': row.get('Razão', '').strip(),
                            }
                        elif selected_maquina == 'SIPAG':
                            # DEBUG: Mostrar todos os campos disponíveis no CSV para SIPAG
                            print(f"DEBUG SIPAG: Campos disponíveis na linha {row_num}: {list(row.keys())}")
                            print(f"DEBUG SIPAG: Valores da linha {row_num}: {row}")

                            # Mapeamento específico para SIPAG na prévia
                            forma_pagamento = row.get('Forma de Pagamento', '').strip()
                            bandeira = row.get('Bandeira', '').strip()
                            valor_bruto = row.get('Valor Bruto', '').strip()
                            taxa_maquinha = row.get('Taxa Máquina', '').strip()
                            valor_liquido = row.get('Valor Líquido', '').strip()
                            numero_autorizacao = row.get('Nº Autorizacao', '').strip()

                            print(f"DEBUG SIPAG: Valores extraídos linha {row_num}:")
                            print(f"  Forma de Pagamento: '{forma_pagamento}'")
                            print(f"  Bandeira: '{bandeira}'")
                            print(f"  Valor Bruto: '{valor_bruto}'")
                            print(f"  Taxa Máquina: '{taxa_maquinha}'")
                            print(f"  Valor Líquido: '{valor_liquido}'")
                            print(f"  N° Autorização: '{numero_autorizacao}'")

                            preview_row = {
                                'linha': row_num - 1,
                                'data_pagamento': data_pagamento,
                                'forma_pagamento': forma_pagamento,
                                'bandeira': bandeira,
                                'valor_bruto': valor_bruto,
                                'taxa_maquinha': taxa_maquinha,
                                'valor_liquido': valor_liquido,
                                'maquinha': 'SIPAG',
                                'numero_autorizacao': numero_autorizacao,
                                'data_venda': data_pagamento,  # Usar data de pagamento como data de venda
                                'nsu_doc': numero_autorizacao,  # Usar autorização como NSU/DOC
                                'parcelas': '1',  # Default para SIPAG
                                'total_parcelas': '1',  # Default para SIPAG
                                'conciliado': row.get('Conciliado', '').strip(),
                                'nota_fiscal': row.get('Nota Fiscal', '').strip(),
                                'razao': row.get('Razão', '').strip(),
                            }
                        else:
                            # Mapeamento padrão para outras máquinas
                            preview_row = {
                                'linha': row_num - 1,
                                'data_pagamento': data_pagamento,
                                'forma_pagamento': row.get('Forma de Pagamento', '').strip(),
                                'bandeira': row.get('Bandeira', '').strip(),
                                'valor_bruto': row.get('Valor parcela bruto', '').strip(),
                                'taxa_maquinha': row.get('Desconto parcela', '').strip(),
                                'valor_liquido': row.get('Valor parcela liquido', '').strip(),
                                'maquinha': selected_maquina,  # Usar a máquina selecionada
                                'numero_autorizacao': (
                                    row.get('Número da autorização') or
                                    row.get('Numero da autorizacao') or
                                    row.get('Autorizacao') or
                                    row.get('Número da Autorização') or
                                    row.get('Numero da Autorizacao') or
                                    ''
                                ).strip(),
                                'data_venda': row.get('Data da transação', '').strip(),
                                'parcelas': row.get('Parcela', '').strip(),
                                'total_parcelas': row.get('Total de parcela', '').strip(),
                                'conciliado': row.get('Conciliado', '').strip(),
                                'nota_fiscal': row.get('Nota Fiscal', '').strip(),
                                'razao': row.get('Razão', '').strip(),
                            }
                        preview_data.append(preview_row)
                        total_rows += 1
                        valid_rows += 1

                    except Exception as e:
                        errors.append(f"Linha {row_num}: Erro na validação - {str(e)}")
                        invalid_rows += 1

                # Salvar dados do arquivo na sessão para importação posterior
                request.session['csv_preview_data'] = {
                    'filename': csv_file.name,
                    'content': decoded_file,
                    'empresa_id': empresa.id,
                    'total_rows': total_rows,
                    'valid_rows': valid_rows,
                    'invalid_rows': invalid_rows,
                    'selected_maquina': selected_maquina
                }
                request.session.modified = True  # Forçar salvamento da sessão

                return render(request, 'relatoriorecebiveis/import_csv_preview.html', {
                    'title': 'Prévia da Importação CSV',
                    'preview_data': preview_data,
                    'errors': errors,
                    'filename': csv_file.name,
                    'empresa': empresa,
                    'selected_maquina': selected_maquina,
                    'total_rows': total_rows,
                    'valid_rows': valid_rows,
                    'invalid_rows': invalid_rows,
                    'confirm_import_url': reverse('relatoriorecebiveis:import_csv'),
                    'back_upload_url': reverse('relatoriorecebiveis:import_csv'),
                })

            except UnicodeDecodeError:
                messages.error(request, 'Erro ao ler o arquivo. Verifique se está em formato UTF-8.')
                return redirect('relatoriorecebiveis:import_csv')
            except Exception as e:
                messages.error(request, f'Erro ao processar o arquivo: {str(e)}')
                return redirect('relatoriorecebiveis:import_csv')
        else:
            messages.error(request, 'Formulário inválido. Verifique os dados inseridos.')
            return redirect('relatoriorecebiveis:import_csv')

    else:
        form = CSVImportForm()

    return render(request, 'relatoriorecebiveis/import_csv.html', {
        'title': 'Importar Relatórios CSV',
        'form': form
    })


def _process_csv_import(request):
    """Processa a importação real do CSV após confirmação"""
    try:
        # Recuperar dados da sessão
        csv_data = request.session.get('csv_preview_data')
        if not csv_data:
            messages.error(request, 'Dados da prévia não encontrados. Faça upload do arquivo novamente.')
            return redirect('relatoriorecebiveis:import_csv')

        # Verificar se os dados da sessão estão corretos

        # Obter empresa
        try:
            empresa_id = csv_data.get('empresa_id')
            empresa = Empresa.objects.get(id=empresa_id)
        except Empresa.DoesNotExist:
            messages.error(request, 'Empresa não encontrada.')
            return redirect('relatoriorecebiveis:relReclist')
        except Exception as e:
            messages.error(request, f'Erro ao obter empresa: {str(e)}')
            return redirect('relatoriorecebiveis:relReclist')

        # Layout Stone: linhas já normalizadas na prévia
        if csv_data.get('selected_maquina') == 'STONE' and csv_data.get('rows'):
            from decimal import Decimal, InvalidOperation

            def _to_decimal(raw):
                if raw is None or raw == '':
                    return None
                try:
                    return Decimal(str(raw).replace(',', '.'))
                except (InvalidOperation, ValueError):
                    return None

            success_count = 0
            error_count = 0
            errors = []
            with transaction.atomic():
                for row_num, row in enumerate(csv_data['rows'], start=1):
                    try:
                        relatorio = RelatorioRecebiveisMaquinaCartao()
                        relatorio.empresa = empresa
                        data_str = (row.get('data_pagamento') or '').strip()
                        if not data_str:
                            continue
                        parsed = False
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                                parsed = True
                                break
                            except ValueError:
                                continue
                        if not parsed:
                            raise ValueError(f'Formato de data inválido: {data_str}')

                        relatorio.forma_pagamento = (row.get('forma_pagamento') or '').strip()
                        relatorio.bandeira = (row.get('bandeira') or '').strip()
                        vb = _to_decimal(row.get('valor_bruto'))
                        if vb is not None:
                            relatorio.valor_bruto = vb
                        taxa = _to_decimal(row.get('taxa_maquinha'))
                        if taxa is not None:
                            taxa = abs(taxa)
                            if taxa > Decimal('999.99'):
                                taxa = Decimal('999.99')
                            relatorio.taxa_maquinha = taxa
                        vl = _to_decimal(row.get('valor_liquido'))
                        if vl is not None:
                            relatorio.valor_liquido = vl
                        relatorio.maquinha = 'STONE'
                        relatorio.numero_autorizacao = (row.get('numero_autorizacao') or '').strip()
                        relatorio.data_venda = (row.get('data_venda') or '').strip()
                        relatorio.nsu_doc = (row.get('nsu_doc') or '').strip() or relatorio.numero_autorizacao
                        parcelas_str = (row.get('parcelas') or '1').strip()
                        total_str = (row.get('total_parcelas') or parcelas_str).strip()
                        relatorio.parcelas = int(parcelas_str) if parcelas_str.isdigit() else 1
                        relatorio.total_parcelas = int(total_str) if total_str.isdigit() else relatorio.parcelas
                        relatorio.parcela_texto = (row.get('parcela_texto') or '').strip() or (
                            f'{relatorio.parcelas} / {relatorio.total_parcelas}'
                        )
                        relatorio.conciliado = False
                        relatorio.nota_fiscal = (row.get('nota_fiscal') or '').strip()
                        relatorio.razao = (row.get('razao') or '').strip()
                        conta_bancaria = (row.get('conta_bancaria') or '').strip()
                        if conta_bancaria:
                            relatorio.conta_bancaria = conta_bancaria[:500]
                        relatorio.save()
                        success_count += 1
                    except Exception as e:
                        errors.append(f'Linha {row_num}: {str(e)}')
                        error_count += 1
                        continue

            if 'csv_preview_data' in request.session:
                del request.session['csv_preview_data']
            request.session.modified = True
            if success_count > 0:
                messages.success(request, f'{success_count} relatório(s) importado(s) do CSV Stone.')
            if error_count > 0:
                messages.warning(request, f'{error_count} linha(s) com erro foram ignoradas.')
                for err in errors[:5]:
                    messages.error(request, err)
            return redirect('relatoriorecebiveis:relReclist')

        # Processar arquivo
        io_string = io.StringIO(csv_data['content'])
        reader = csv.DictReader(io_string, delimiter=';')

        success_count = 0
        error_count = 0
        errors = []

        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                try:
                    # Mapeia os campos do CSV para o modelo
                    relatorio = RelatorioRecebiveisMaquinaCartao()
                    relatorio.empresa = empresa

                    selected_maquina = csv_data.get('selected_maquina', 'OUTROS')

                    if selected_maquina == 'CIELO':
                        # Mapeamento específico para CIELO
                        # DATA DE PAGAMENTO - Campo obrigatório para importação
                        data_str = None
                        data_field_names = [
                            'Data de pagamento',  # Com acento
                            'Data do pagamento',  # Com acento
                            'Data de Pagamento',  # Com acento maiúsculo
                            'Data do Pagamento',  # Com acento maiúsculo
                            'data de pagamento',  # Minúsculo
                            'data do pagamento',  # Minúsculo
                            'Data_pagamento',     # Com underscore
                            'Data_pagamento',     # Com underscore
                        ]

                        for field_name in data_field_names:
                            if field_name in row and row[field_name].strip():
                                data_str = row[field_name].strip()
                                break

                        if not data_str:
                            continue  # Ignorar lançamento sem data de pagamento
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                                break
                            except ValueError:
                                continue
                        else:
                            raise ValueError(f"Formato de data inválido: {data_str}")

                        # FORMA DE PAGAMENTO
                        relatorio.forma_pagamento = row.get('Forma de pagamento', '').strip()

                        # BANDEIRA
                        relatorio.bandeira = row.get('Bandeira', '').strip()

                        # VALOR BRUTO
                        if row.get('Valor bruto'):
                            relatorio.valor_bruto = _parse_currency_value(row['Valor bruto'])

                        # TAXA DE MAQUININHA
                        if row.get('Valor Taxa'):
                            taxa_value = _parse_currency_value(row['Valor Taxa'])
                            if taxa_value is not None:
                                relatorio.taxa_maquinha = taxa_value

                        # VALOR LÍQUIDO
                        if row.get('Valor liquido'):
                            relatorio.valor_liquido = _parse_currency_value(row['Valor liquido'])

                        # MAQUININHA
                        relatorio.maquinha = 'CIELO'

                        # N° AUTORIZAÇÃO
                        relatorio.numero_autorizacao = row.get('N. Autorizacao', '').strip()

                        # DATA DA VENDA
                        relatorio.data_venda = row.get('Data da venda', '').strip()

                        # NSU/DOC
                        relatorio.nsu_doc = row.get('NSU/DOC', '').strip()

                        # PARCELAS e TOTAL PARCELAS - Lógica especial para CIELO
                        forma_pagamento_lower = relatorio.forma_pagamento.lower() if relatorio.forma_pagamento else ''
                        is_debito = 'debito' in forma_pagamento_lower or 'débito' in forma_pagamento_lower

                        if is_debito:
                            relatorio.parcelas = 1
                            relatorio.total_parcelas = 1
                        else:
                            # Número da parcela
                            parcela_str = row.get('Número da parcela', '').strip()
                            if parcela_str and parcela_str.isdigit():
                                relatorio.parcelas = int(parcela_str)
                            else:
                                relatorio.parcelas = 1

                            # Quantidade total de parcelas
                            total_parcela_str = row.get('Quantidade total de parcelas', '').strip()
                            if total_parcela_str and total_parcela_str.isdigit():
                                relatorio.total_parcelas = int(total_parcela_str)
                            else:
                                relatorio.total_parcelas = 1
                    elif selected_maquina == 'INFINTY':
                        # Mapeamento específico para INFINTY
                        # DATA DE PAGAMENTO - Campo obrigatório para importação
                        data_str = None
                        data_field_names = [
                            'Data Pagamento',  # Campo específico do INFINTY
                            'Data de pagamento',  # Com acento
                            'Data do pagamento',  # Com acento
                            'Data de Pagamento',  # Com acento maiúsculo
                            'Data do Pagamento',  # Com acento maiúsculo
                            'data de pagamento',  # Minúsculo
                            'data do pagamento',  # Minúsculo
                            'Data_pagamento',     # Com underscore
                            'Data_pagamento',     # Com underscore
                        ]

                        for field_name in data_field_names:
                            if field_name in row and row[field_name].strip():
                                data_str = row[field_name].strip()
                                break

                        if not data_str:
                            continue  # Ignorar lançamento sem data de pagamento
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                                break
                            except ValueError:
                                continue
                        else:
                            raise ValueError(f"Formato de data inválido: {data_str}")

                        # FORMA DE PAGAMENTO
                        relatorio.forma_pagamento = row.get('Forma Pagamento', '').strip()

                        # BANDEIRA
                        relatorio.bandeira = row.get('Bandeira', '').strip()

                        # VALOR BRUTO
                        if row.get('Valor Bruto'):
                            relatorio.valor_bruto = _parse_currency_value(row['Valor Bruto'])

                        # TAXA DE MAQUININHA - Tentar variações do campo Taxa
                        taxa_value = None
                        if row.get('Valor Taxa'):
                            taxa_value = _parse_currency_value(row['Valor Taxa'])
                        elif row.get('Taxa Máquina'):
                            taxa_value = _parse_currency_value(row['Taxa Máquina'])

                        if taxa_value is not None:
                            relatorio.taxa_maquinha = taxa_value

                        # VALOR LÍQUIDO - Tentar variações com e sem acento
                        valor_liquido_field = row.get('Valor Líquido') or row.get('Valor Liquido')
                        if valor_liquido_field:
                            relatorio.valor_liquido = _parse_currency_value(valor_liquido_field)

                        # MAQUININHA
                        relatorio.maquinha = 'INFINTY'

                        # N° AUTORIZAÇÃO - Tentar variações do campo Autorização
                        relatorio.numero_autorizacao = (
                            row.get('Autorização', '').strip() or
                            row.get('N° Autorização', '').strip() or
                            row.get('Autorizacao', '').strip()
                        )

                        # DATA DA VENDA
                        relatorio.data_venda = row.get('Data Venda', '').strip()

                        # NSU/DOC - Usar o número de autorização como NSU/DOC
                        relatorio.nsu_doc = row.get('N° Autorização', '').strip()

                        # PARCELAS - Tentar variações do campo Parcelas
                        parcelas_str = (
                            row.get('Parcelas', '').strip() or
                            row.get('Número da parcela', '').strip() or
                            row.get('Parcela', '').strip()
                        )

                        if parcelas_str and parcelas_str.isdigit():
                            relatorio.parcelas = int(parcelas_str)
                        else:
                            relatorio.parcelas = 1

                        # TOTAL PARCELAS - Tentar variações do campo Total de Parcelas
                        total_parcelas_str = (
                            row.get('Total de Parcelas', '').strip() or
                            row.get('Quantidade total de parcelas', '').strip() or
                            row.get('Total de parcela', '').strip()
                        )

                        if total_parcelas_str and total_parcelas_str.isdigit():
                            relatorio.total_parcelas = int(total_parcelas_str)
                        else:
                            relatorio.total_parcelas = relatorio.parcelas  # Mesmo valor se não encontrar
                    elif selected_maquina == 'SIPAG':
                        # DEBUG: Mostrar todos os campos disponíveis no CSV para SIPAG
                        print(f"DEBUG SIPAG PROCESS: Campos disponíveis na linha {row_num}: {list(row.keys())}")
                        print(f"DEBUG SIPAG PROCESS: Valores da linha {row_num}: {row}")

                        # Mapeamento específico para SIPAG
                        # DATA DE PAGAMENTO - Campo obrigatório para importação
                        data_str = None
                        data_field_names = [
                            'Data de pagamento',  # Com acento
                            'Data do pagamento',  # Com acento
                            'Data de Pagamento',  # Com acento maiúsculo
                            'Data do Pagamento',  # Com acento maiúsculo
                            'data de pagamento',  # Minúsculo
                            'data do pagamento',  # Minúsculo
                            'Data_pagamento',     # Com underscore
                            'Data_pagamento',     # Com underscore
                        ]

                        for field_name in data_field_names:
                            if field_name in row and row[field_name].strip():
                                data_str = row[field_name].strip()
                                break

                        if not data_str:
                            continue  # Ignorar lançamento sem data de pagamento
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                                break
                            except ValueError:
                                continue
                        else:
                            raise ValueError(f"Formato de data inválido: {data_str}")

                        # FORMA DE PAGAMENTO
                        relatorio.forma_pagamento = row.get('Forma de Pagamento', '').strip()

                        # BANDEIRA
                        relatorio.bandeira = row.get('Bandeira', '').strip()

                        # VALOR BRUTO
                        if row.get('Valor Bruto'):
                            relatorio.valor_bruto = _parse_currency_value(row['Valor Bruto'])

                        # TAXA DE MAQUININHA
                        if row.get('Taxa Máquina'):
                            taxa_value = _parse_currency_value(row['Taxa Máquina'])
                            if taxa_value is not None:
                                relatorio.taxa_maquinha = taxa_value

                        # VALOR LÍQUIDO
                        if row.get('Valor Líquido'):
                            relatorio.valor_liquido = _parse_currency_value(row['Valor Líquido'])

                        # MAQUININHA
                        relatorio.maquinha = 'SIPAG'

                        # N° AUTORIZAÇÃO - Usar exatamente o mesmo campo que funciona na prévia
                        numero_autorizacao_raw = row.get('Nº Autorizacao', '').strip()
                        print(f"DEBUG SIPAG: Campo 'Nº Autorizacao' encontrado: '{numero_autorizacao_raw}'")

                        # Se não encontrou, tentar outras variações
                        if not numero_autorizacao_raw:
                            autorizacao_field_names = [
                                'N° Autorização',      # Com grau e acento
                                'N° Autorizacao',      # Com grau sem acento
                                'Nº Autorização',      # Com ordinal e acento
                                'N Autorização',       # Sem símbolo
                                'N Autorizacao',       # Sem símbolo sem acento
                                'Numero Autorização',  # Numero com acento
                                'Numero Autorizacao',  # Numero sem acento
                                'Autorização',         # Apenas autorização com acento
                                'Autorizacao',         # Apenas autorização sem acento
                                'numero_autorizacao',  # Minúsculo com underscore
                                'N_Autorizacao',       # Com underscore
                            ]

                            for field_name in autorizacao_field_names:
                                if field_name in row and row[field_name].strip():
                                    numero_autorizacao_raw = row[field_name].strip()
                                    print(f"DEBUG SIPAG: Campo alternativo de autorização encontrado: '{field_name}' = '{numero_autorizacao_raw}'")
                                    break

                        relatorio.numero_autorizacao = numero_autorizacao_raw
                        print(f"DEBUG SIPAG: N° Autorização final: '{relatorio.numero_autorizacao}'")

                        # DATA DA VENDA - Usar data de pagamento como data de venda
                        relatorio.data_venda = data_str

                        # NSU/DOC - Usar autorização como NSU/DOC
                        relatorio.nsu_doc = relatorio.numero_autorizacao

                        # PARCELAS - Default para SIPAG
                        relatorio.parcelas = 1

                        # TOTAL PARCELAS - Default para SIPAG
                        relatorio.total_parcelas = 1

                        print(f"DEBUG SIPAG PROCESS: Valores salvos linha {row_num}:")
                        print(f"  Data Pagamento: {relatorio.data_pagamento}")
                        print(f"  Forma Pagamento: '{relatorio.forma_pagamento}'")
                        print(f"  Bandeira: '{relatorio.bandeira}'")
                        print(f"  Valor Bruto: {relatorio.valor_bruto}")
                        print(f"  Taxa Máquina: {relatorio.taxa_maquinha}")
                        print(f"  Valor Líquido: {relatorio.valor_liquido}")
                        print(f"  N° Autorização: '{relatorio.numero_autorizacao}'")

                        # DEBUG: Verificar se o relatório tem o campo preenchido antes de salvar
                        print(f"DEBUG SIPAG: Antes de salvar - relatorio.numero_autorizacao = '{relatorio.numero_autorizacao}'")
                    else:
                        # Mapeamento padrão para outras máquinas
                        # DATA DE PAGAMENTO - Campo obrigatório para importação
                        data_str = None
                        data_field_names = [
                            'Data de pagamento',  # Com acento
                            'Data do pagamento',  # Com acento
                            'Data de Pagamento',  # Com acento maiúsculo
                            'Data do Pagamento',  # Com acento maiúsculo
                            'data de pagamento',  # Minúsculo
                            'data do pagamento',  # Minúsculo
                            'Data_pagamento',     # Com underscore
                            'Data_pagamento',     # Com underscore
                        ]

                        for field_name in data_field_names:
                            if field_name in row and row[field_name].strip():
                                data_str = row[field_name].strip()
                                break

                        if not data_str:
                            continue  # Ignorar lançamento sem data de pagamento
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                                break
                            except ValueError:
                                continue
                        else:
                            raise ValueError(f"Formato de data inválido: {data_str}")

                        # FORMA DE PAGAMENTO
                        relatorio.forma_pagamento = row.get('Forma de Pagamento', '').strip()

                        # BANDEIRA
                        relatorio.bandeira = row.get('Bandeira', '').strip()

                        # VALOR BRUTO
                        if row.get('Valor parcela bruto'):
                            relatorio.valor_bruto = _parse_currency_value(row['Valor parcela bruto'])

                        # TAXA DE MAQUININHA
                        if row.get('Desconto parcela'):
                            taxa_value = _parse_currency_value(row['Desconto parcela'])
                            if taxa_value is not None:
                                relatorio.taxa_maquinha = taxa_value

                        # VALOR LÍQUIDO
                        if row.get('Valor parcela liquido'):
                            relatorio.valor_liquido = _parse_currency_value(row['Valor parcela liquido'])

                        # MAQUININHA - Usar a máquina selecionada na tela de importação
                        relatorio.maquinha = selected_maquina

                        # N° AUTORIZAÇÃO
                        relatorio.numero_autorizacao = (
                            row.get('Número da autorização') or
                            row.get('Numero da autorizacao') or
                            row.get('Autorizacao') or
                            row.get('Número da Autorização') or
                            row.get('Numero da Autorizacao') or
                            ''
                        ).strip()

                        # DATA DA VENDA
                        relatorio.data_venda = row.get('Data da transação', '').strip()

                        # NSU/DOC
                        relatorio.nsu_doc = (
                            row.get('Número da autorização') or
                            row.get('Numero da autorizacao') or
                            row.get('Autorizacao') or
                            row.get('Número da Autorização') or
                            row.get('Numero da Autorizacao') or
                            ''
                        ).strip()

                        # PARCELAS
                        if row.get('Parcela'):
                            relatorio.parcelas = int(row['Parcela'].strip())

                        # TOTAL PARCELAS
                        if row.get('Total de parcela'):
                            relatorio.total_parcelas = int(row['Total de parcela'].strip())

                    # CONCILIADO - Para importação de relatório de recebíveis, sempre definir como False
                    relatorio.conciliado = False

                    # IDENTIFICAÇÃO EXTRATO
                    relatorio.identificacao_extrato = row.get('Identificação Extrato', '').strip()

                    # NOTA FISCAL
                    relatorio.nota_fiscal = row.get('Nota Fiscal', '').strip()

                    # RAZÃO
                    relatorio.razao = row.get('Razão', '').strip()

                    # DEBUG: Verificar se o relatório tem o campo preenchido antes de salvar
                    print(f"DEBUG SIPAG: Antes de salvar - relatorio.numero_autorizacao = '{relatorio.numero_autorizacao}'")
                    print(f"DEBUG SIPAG: Tipo do campo numero_autorizacao: {type(relatorio.numero_autorizacao)}")

                    # Salva o relatório
                    relatorio.save()
                    success_count += 1

                    # DEBUG: Verificar se o relatório foi salvo corretamente
                    relatorio_salvo = RelatorioRecebiveisMaquinaCartao.objects.get(id=relatorio.id)
                    print(f"DEBUG SIPAG: Após salvar - relatorio.numero_autorizacao = '{relatorio_salvo.numero_autorizacao}'")

                except Exception as e:
                    errors.append(f"Linha {row_num}: Erro inesperado - {str(e)}")
                    error_count += 1
                    continue

        # Limpar dados da sessão
        if 'csv_preview_data' in request.session:
            del request.session['csv_preview_data']

        # Mostrar contagens finais

        # Mensagens de resultado
        if success_count > 0:
            messages.success(request, f'{success_count} relatórios importados com sucesso!')

        if error_count > 0:
            messages.warning(request, f'{error_count} linhas com erro foram ignoradas.')
            for error in errors[:5]:
                messages.error(request, error)
            if len(errors) > 5:
                messages.error(request, f'... e mais {len(errors) - 5} erros.')

        return redirect('relatoriorecebiveis:relReclist')

    except Exception as e:
        messages.error(request, f'Erro inesperado: {str(e)}')
        return redirect('relatoriorecebiveis:import_csv')


def _empresa_para_import_recebiveis(request):
    """Empresa da sessão ou primeira associada ao usuário (mesmo padrão da importação CSV)."""
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        try:
            return Empresa.objects.get(id=empresa_id)
        except Empresa.DoesNotExist:
            pass
    usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
    if not usuario_empresa:
        usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
    if not usuario_empresa:
        return None
    return usuario_empresa.empresa


def _process_infinitepay_pdf_import(request):
    """Grava linhas já parseadas (formato INFINTY) com maquinha INFINITEPAY."""
    pdf_data = request.session.get('infinitepay_pdf_preview_data')
    if not pdf_data:
        messages.error(request, 'Dados da prévia não encontrados. Envie o PDF novamente.')
        return redirect('relatoriorecebiveis:import_pdf_infinitepay')

    try:
        empresa = Empresa.objects.get(id=pdf_data['empresa_id'])
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada.')
        return redirect('relatoriorecebiveis:relReclist')

    rows = pdf_data.get('rows') or []
    success_count = 0
    error_count = 0
    errors = []

    with transaction.atomic():
        for row_num, row in enumerate(rows, start=1):
            try:
                relatorio = RelatorioRecebiveisMaquinaCartao()
                relatorio.empresa = empresa

                data_str = (row.get('Data Pagamento') or '').strip()
                if not data_str:
                    continue
                parsed = False
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                    try:
                        relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                        parsed = True
                        break
                    except ValueError:
                        continue
                if not parsed:
                    raise ValueError(f"Formato de data inválido: {data_str}")

                relatorio.forma_pagamento = (row.get('Forma Pagamento') or '').strip()
                relatorio.bandeira = (row.get('Bandeira') or '').strip()

                if row.get('Valor Bruto'):
                    relatorio.valor_bruto = _parse_currency_value(row['Valor Bruto'])

                taxa_value = None
                if row.get('Valor Taxa'):
                    taxa_value = _parse_currency_value(row['Valor Taxa'])
                elif row.get('Taxa Máquina'):
                    taxa_value = _parse_currency_value(row['Taxa Máquina'])
                if taxa_value is not None:
                    relatorio.taxa_maquinha = taxa_value

                valor_liquido_field = row.get('Valor Líquido') or row.get('Valor Liquido')
                if valor_liquido_field:
                    relatorio.valor_liquido = _parse_currency_value(valor_liquido_field)

                relatorio.maquinha = 'INFINITEPAY'

                relatorio.numero_autorizacao = (
                    (row.get('Autorização') or '').strip() or
                    (row.get('N° Autorização') or '').strip() or
                    (row.get('Autorizacao') or '').strip()
                )
                relatorio.data_venda = (row.get('Data Venda') or '').strip()
                relatorio.nsu_doc = (row.get('N° Autorização') or '').strip() or relatorio.numero_autorizacao

                parcela_col = (row.get('Parcela') or '').strip()
                if parcela_col:
                    relatorio.parcela_texto = _normalize_parcela_display(parcela_col)
                    pm = re.search(r'(\d+)\s*/\s*(\d+)', parcela_col)
                    if pm:
                        relatorio.parcelas = int(pm.group(1))
                        relatorio.total_parcelas = int(pm.group(2))
                    else:
                        relatorio.parcelas = 1
                        relatorio.total_parcelas = 1
                else:
                    parcelas_str = (
                        (row.get('Parcelas') or '').strip() or
                        (row.get('Número da parcela') or '').strip()
                    )
                    if parcelas_str and parcelas_str.isdigit():
                        relatorio.parcelas = int(parcelas_str)
                    else:
                        relatorio.parcelas = 1

                    total_parcelas_str = (
                        (row.get('Total de Parcelas') or '').strip() or
                        (row.get('Quantidade total de parcelas') or '').strip() or
                        (row.get('Total de parcela') or '').strip()
                    )
                    if total_parcelas_str and total_parcelas_str.isdigit():
                        relatorio.total_parcelas = int(total_parcelas_str)
                    else:
                        relatorio.total_parcelas = relatorio.parcelas

                relatorio.conciliado = False
                relatorio.identificacao_extrato = (row.get('Identificação Extrato') or '').strip()
                relatorio.nota_fiscal = (row.get('Nota Fiscal') or '').strip()
                relatorio.razao = (row.get('Razão') or '').strip()

                relatorio.save()
                success_count += 1
            except Exception as e:
                errors.append(f'Linha {row_num}: {str(e)}')
                error_count += 1
                continue

    if 'infinitepay_pdf_preview_data' in request.session:
        del request.session['infinitepay_pdf_preview_data']
    request.session.modified = True

    if success_count > 0:
        messages.success(request, f'{success_count} relatório(s) importado(s) do PDF Infinite Pay.')
    if error_count > 0:
        messages.warning(request, f'{error_count} linha(s) com erro foram ignoradas.')
        for err in errors[:5]:
            messages.error(request, err)
        if len(errors) > 5:
            messages.error(request, f'... e mais {len(errors) - 5} erro(s).')

    return redirect('relatoriorecebiveis:relReclist')


@login_required
def relatorio_recebiveis_import_pdf_infinitepay(request):
    """Importa relatório PDF Infinite Pay (Conta Web / recebimentos)."""
    if request.method == 'POST' and 'confirm_import' in request.POST:
        return _process_infinitepay_pdf_import(request)

    if request.method == 'POST':
        form = InfinitePayPDFImportForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.cleaned_data['pdf_file']
            if pdf_file.size == 0:
                messages.error(request, 'O arquivo selecionado está vazio.')
                return redirect('relatoriorecebiveis:import_pdf_infinitepay')
            if not pdf_file.name.lower().endswith('.pdf'):
                messages.error(request, 'O arquivo deve ter extensão .pdf')
                return redirect('relatoriorecebiveis:import_pdf_infinitepay')

            try:
                empresa = _empresa_para_import_recebiveis(request)
                if not empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('relatoriorecebiveis:relReclist')
            except Empresa.DoesNotExist:
                messages.error(request, 'Empresa selecionada não encontrada.')
                return redirect('relatoriorecebiveis:relReclist')

            try:
                pdf_bytes = pdf_file.read()
                use_gemini = form.cleaned_data.get('extrair_com_gemini')
                fonte_extracao = 'local'
                pdf_warnings: list = []
                rows: list = []
                if use_gemini:
                    ok_key, api_key_msg = validate_gemini_api_key()
                    if not ok_key:
                        messages.error(request, api_key_msg)
                    else:
                        rows, gw = parse_infinitepay_pdf_with_gemini(pdf_bytes, pdf_file.name)
                        pdf_warnings.extend(gw)
                        if rows:
                            fonte_extracao = 'gemini'
                        else:
                            messages.warning(
                                request,
                                'Extração com Gemini não retornou linhas ou a API não está disponível; '
                                'foi usada a leitura local (pdfplumber).',
                            )
                if not rows:
                    rows, lw = parse_infinitepay_pdf_bytes(pdf_bytes)
                    pdf_warnings.extend(lw)
            except Exception as e:
                messages.error(request, f'Erro ao ler o PDF: {str(e)}')
                return redirect('relatoriorecebiveis:import_pdf_infinitepay')

            preview_data = []
            errors = list(pdf_warnings)
            total_rows = 0
            valid_rows = 0
            invalid_rows = 0

            for row_num, row in enumerate(rows, start=1):
                data_pagamento = (row.get('Data Pagamento') or '').strip()
                if not data_pagamento:
                    errors.append(f'Linha {row_num}: data de pagamento ausente — ignorada')
                    invalid_rows += 1
                    continue
                data_valida = False
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                    try:
                        datetime.strptime(data_pagamento, fmt).date()
                        data_valida = True
                        break
                    except ValueError:
                        continue
                if not data_valida:
                    errors.append(
                        f"Linha {row_num}: formato de data inválido '{data_pagamento}' — ignorada na importação"
                    )
                    invalid_rows += 1
                    continue

                forma_pagamento = (row.get('Forma Pagamento') or '').strip()
                bandeira = (row.get('Bandeira') or '').strip()
                valor_bruto = (row.get('Valor Bruto') or '').strip()
                taxa_maquinha = (
                    (row.get('Valor Taxa') or '').strip() or
                    (row.get('Taxa Máquina') or '').strip()
                )
                valor_liquido = (
                    (row.get('Valor Líquido') or '').strip() or
                    (row.get('Valor Liquido') or '').strip()
                )
                numero_autorizacao = (
                    (row.get('Autorização') or '').strip() or
                    (row.get('N° Autorização') or '').strip() or
                    (row.get('Autorizacao') or '').strip()
                )
                data_venda = (row.get('Data Venda') or '').strip()
                parcela_txt = (row.get('Parcela') or '').strip()
                if parcela_txt:
                    parcelas = _normalize_parcela_display(parcela_txt)
                    total_parcelas = ''
                else:
                    parcelas = (
                        (row.get('Parcelas') or '').strip() or
                        (row.get('Número da parcela') or '').strip() or
                        '1'
                    )
                    total_parcelas = (
                        (row.get('Total de Parcelas') or '').strip() or
                        (row.get('Quantidade total de parcelas') or '').strip() or
                        (row.get('Total de parcela') or '').strip() or
                        parcelas
                    )

                preview_data.append({
                    'linha': row_num,
                    'data_pagamento': data_pagamento,
                    'forma_pagamento': forma_pagamento,
                    'bandeira': bandeira,
                    'valor_bruto': valor_bruto,
                    'taxa_maquinha': taxa_maquinha,
                    'valor_liquido': valor_liquido,
                    'maquinha': 'INFINITEPAY',
                    'numero_autorizacao': numero_autorizacao,
                    'data_venda': data_venda,
                    'nsu_doc': numero_autorizacao,
                    'parcelas': parcelas,
                    'total_parcelas': total_parcelas,
                    'conciliado': '',
                    'nota_fiscal': '',
                    'razao': '',
                })
                total_rows += 1
                valid_rows += 1

            request.session['infinitepay_pdf_preview_data'] = {
                'filename': pdf_file.name,
                'empresa_id': empresa.id,
                'rows': rows,
                'fonte_extracao': fonte_extracao,
            }
            request.session.modified = True

            return render(request, 'relatoriorecebiveis/import_csv_preview.html', {
                'title': 'Prévia da importação — PDF Infinite Pay',
                'preview_data': preview_data,
                'errors': errors,
                'filename': pdf_file.name,
                'empresa': empresa,
                'selected_maquina': 'INFINITEPAY',
                'total_rows': total_rows,
                'valid_rows': valid_rows,
                'invalid_rows': invalid_rows,
                'confirm_import_url': reverse('relatoriorecebiveis:import_pdf_infinitepay'),
                'back_upload_url': reverse('relatoriorecebiveis:import_pdf_infinitepay'),
                'fonte_extracao': fonte_extracao,
            })
        messages.error(request, 'Formulário inválido. Verifique o arquivo.')
        return redirect('relatoriorecebiveis:import_pdf_infinitepay')

    form = InfinitePayPDFImportForm()
    return render(request, 'relatoriorecebiveis/import_infinitepay_pdf.html', {
        'title': 'Importar PDF — Infinite Pay',
        'form': form,
    })


def _process_cielo_xlsx_import(request):
    """Grava linhas já parseadas do XLSX Cielo."""
    from decimal import Decimal, InvalidOperation

    data = request.session.get('cielo_xlsx_preview_data')
    if not data:
        messages.error(request, 'Dados da prévia não encontrados. Envie o arquivo novamente.')
        return redirect('relatoriorecebiveis:import_xlsx_cielo')

    try:
        empresa = Empresa.objects.get(id=data['empresa_id'])
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada.')
        return redirect('relatoriorecebiveis:relReclist')

    def _to_decimal(raw):
        if raw is None or raw == '':
            return None
        try:
            return Decimal(str(raw).replace(',', '.'))
        except (InvalidOperation, ValueError):
            return None

    rows = data.get('rows') or []
    success_count = 0
    error_count = 0
    errors = []

    with transaction.atomic():
        for row_num, row in enumerate(rows, start=1):
            try:
                relatorio = RelatorioRecebiveisMaquinaCartao()
                relatorio.empresa = empresa

                data_str = (row.get('data_pagamento') or '').strip()
                if not data_str:
                    continue
                parsed = False
                for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                    try:
                        relatorio.data_pagamento = datetime.strptime(data_str, fmt).date()
                        parsed = True
                        break
                    except ValueError:
                        continue
                if not parsed:
                    raise ValueError(f'Formato de data inválido: {data_str}')

                relatorio.forma_pagamento = (row.get('forma_pagamento') or '').strip()
                relatorio.bandeira = (row.get('bandeira') or '').strip()

                vb = _to_decimal(row.get('valor_bruto'))
                if vb is not None:
                    relatorio.valor_bruto = vb

                taxa = _to_decimal(row.get('taxa_maquinha'))
                if taxa is not None:
                    taxa = abs(taxa)
                    # Campo taxa_maquinha: max_digits=5 → até 999.99
                    if taxa > Decimal('999.99'):
                        taxa = Decimal('999.99')
                    relatorio.taxa_maquinha = taxa

                vl = _to_decimal(row.get('valor_liquido'))
                if vl is not None:
                    relatorio.valor_liquido = vl

                relatorio.maquinha = 'CIELO'
                relatorio.numero_autorizacao = (row.get('numero_autorizacao') or '').strip()
                relatorio.data_venda = (row.get('data_venda') or '').strip()
                relatorio.nsu_doc = (row.get('nsu_doc') or '').strip() or relatorio.numero_autorizacao

                parcelas_str = (row.get('parcelas') or '1').strip()
                total_str = (row.get('total_parcelas') or parcelas_str).strip()
                relatorio.parcelas = int(parcelas_str) if parcelas_str.isdigit() else 1
                relatorio.total_parcelas = int(total_str) if total_str.isdigit() else relatorio.parcelas
                relatorio.parcela_texto = (row.get('parcela_texto') or '').strip() or (
                    f'{relatorio.parcelas} / {relatorio.total_parcelas}'
                )

                relatorio.conciliado = False
                relatorio.nota_fiscal = (row.get('nota_fiscal') or '').strip()
                relatorio.razao = (row.get('razao') or '').strip()
                conta_bancaria = (row.get('conta_bancaria') or '').strip()
                if conta_bancaria:
                    relatorio.conta_bancaria = conta_bancaria[:500]

                relatorio.save()
                success_count += 1
            except Exception as e:
                errors.append(f'Linha {row_num}: {str(e)}')
                error_count += 1
                continue

    if 'cielo_xlsx_preview_data' in request.session:
        del request.session['cielo_xlsx_preview_data']
    request.session.modified = True

    if success_count > 0:
        messages.success(request, f'{success_count} relatório(s) importado(s) do XLSX Cielo.')
    if error_count > 0:
        messages.warning(request, f'{error_count} linha(s) com erro foram ignoradas.')
        for err in errors[:5]:
            messages.error(request, err)
        if len(errors) > 5:
            messages.error(request, f'... e mais {len(errors) - 5} erro(s).')

    return redirect('relatoriorecebiveis:relReclist')


@login_required
def relatorio_recebiveis_import_xlsx_cielo(request):
    """Importa relatório detalhado de recebíveis Cielo (.xlsx)."""
    if request.method == 'POST' and 'confirm_import' in request.POST:
        return _process_cielo_xlsx_import(request)

    if request.method == 'POST':
        form = CieloXLSXImportForm(request.POST, request.FILES)
        if form.is_valid():
            xlsx_file = form.cleaned_data['xlsx_file']
            if xlsx_file.size == 0:
                messages.error(request, 'O arquivo selecionado está vazio.')
                return redirect('relatoriorecebiveis:import_xlsx_cielo')
            name_l = xlsx_file.name.lower()
            if not (name_l.endswith('.xlsx') or name_l.endswith('.xlsm')):
                messages.error(request, 'O arquivo deve ter extensão .xlsx')
                return redirect('relatoriorecebiveis:import_xlsx_cielo')

            try:
                empresa = _empresa_para_import_recebiveis(request)
                if not empresa:
                    messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                    return redirect('relatoriorecebiveis:relReclist')
            except Empresa.DoesNotExist:
                messages.error(request, 'Empresa selecionada não encontrada.')
                return redirect('relatoriorecebiveis:relReclist')

            try:
                file_bytes = xlsx_file.read()
                rows, parse_warnings = parse_cielo_xlsx_bytes(file_bytes)
            except Exception as e:
                messages.error(request, f'Erro ao ler o Excel: {str(e)}')
                return redirect('relatoriorecebiveis:import_xlsx_cielo')

            preview_data = []
            errors = list(parse_warnings)
            total_rows = 0
            valid_rows = 0
            invalid_rows = len(parse_warnings)

            for row in rows:
                total_rows += 1
                valid_rows += 1
                preview_data.append({
                    'linha': row.get('linha'),
                    'data_pagamento': row.get('data_pagamento'),
                    'forma_pagamento': row.get('forma_pagamento'),
                    'bandeira': row.get('bandeira'),
                    'valor_bruto': row.get('valor_bruto'),
                    'taxa_maquinha': row.get('taxa_maquinha'),
                    'valor_liquido': row.get('valor_liquido'),
                    'maquinha': 'CIELO',
                    'numero_autorizacao': row.get('numero_autorizacao'),
                    'data_venda': row.get('data_venda'),
                    'parcelas': row.get('parcela_texto') or row.get('parcelas'),
                    'conciliado': row.get('conciliado') or 'Não',
                    'nota_fiscal': row.get('nota_fiscal'),
                })

            if not preview_data:
                for w in parse_warnings[:8]:
                    messages.warning(request, w)
                messages.error(request, 'Nenhum recebível válido encontrado no arquivo.')
                return redirect('relatoriorecebiveis:import_xlsx_cielo')

            request.session['cielo_xlsx_preview_data'] = {
                'filename': xlsx_file.name,
                'empresa_id': empresa.id,
                'rows': rows,
            }
            request.session.modified = True

            return render(request, 'relatoriorecebiveis/import_csv_preview.html', {
                'title': 'Prévia da importação — XLSX Cielo',
                'preview_data': preview_data,
                'errors': errors,
                'filename': xlsx_file.name,
                'empresa': empresa,
                'selected_maquina': 'CIELO',
                'total_rows': total_rows,
                'valid_rows': valid_rows,
                'invalid_rows': invalid_rows,
                'confirm_import_url': reverse('relatoriorecebiveis:import_xlsx_cielo'),
                'back_upload_url': reverse('relatoriorecebiveis:import_xlsx_cielo'),
            })
        messages.error(request, 'Formulário inválido. Verifique o arquivo.')
        return redirect('relatoriorecebiveis:import_xlsx_cielo')

    form = CieloXLSXImportForm()
    return render(request, 'relatoriorecebiveis/import_cielo_xlsx.html', {
        'title': 'Importar XLSX — Cielo',
        'form': form,
    })


@login_required
def relatorio_recebiveis_conciliate(request):
    """Conciliar relatórios de recebíveis com extrato bancário seguindo especificações exatas"""
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_ids')
        if not selected_ids:
            messages.warning(request, 'Nenhum relatório selecionado para conciliação.')
            return redirect('relatoriorecebiveis:relReclist')

        # Obter empresa do usuário da sessão
        try:
            empresa_id = request.session.get('empresa_id')
            if empresa_id:
                empresa = Empresa.objects.get(id=empresa_id)
            else:
                # Fallback: tenta encontrar empresa ativa do usuário
                usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user, ativo=True).first()
                if not usuario_empresa:
                    # Se não encontrou empresa ativa, tenta qualquer empresa associada ao usuário
                    usuario_empresa = UsuarioEmpresa.objects.filter(usuario=request.user).first()
                    if not usuario_empresa:
                        messages.error(request, 'Usuário não está associado a nenhuma empresa.')
                        return redirect('relatoriorecebiveis:relReclist')
                empresa = usuario_empresa.empresa
        except Empresa.DoesNotExist:
            messages.error(request, 'Empresa selecionada não encontrada.')
            return redirect('relatoriorecebiveis:relReclist')
        except Exception as e:
            messages.error(request, f'Erro ao obter empresa do usuário: {str(e)}')
            return redirect('relatoriorecebiveis:relReclist')

        # Obter relatórios selecionados que não estão conciliados
        relatorios = RelatorioRecebiveisMaquinaCartao.objects.filter(
            id__in=selected_ids,
            conciliado=False,
            empresa=empresa
        )

        if not relatorios:
            messages.warning(request, 'Nenhum relatório elegível para conciliação.')
            return redirect('relatoriorecebiveis:relReclist')

        conciliados = 0

        # DEBUG: Mostrar valores agrupados por forma_pagamento, bandeira, data_pagamento e maquinha
        from collections import defaultdict
        grupos = defaultdict(list)

        print("DEBUG CONCILIACAO: Relatórios selecionados para conciliação (agrupados):")
        for r in relatorios:
            chave = (r.forma_pagamento or 'N/A', r.bandeira or 'N/A', r.data_pagamento, r.maquinha or 'N/A')
            grupos[chave].append(r)
            print(f"  ID {r.id}: {r.maquinha} - {r.forma_pagamento} - {r.bandeira} - {r.data_pagamento} - Valor líquido R$ {r.valor_liquido:.2f}")

        print("\nDEBUG CONCILIACAO: Somas por grupo (forma_pagamento, bandeira, data_pagamento, maquinha):")
        total_valor_liquido = 0
        for chave, relatorios_grupo in grupos.items():
            forma_pagamento, bandeira, data_pagamento, maquinha = chave
            soma_grupo = sum(r.valor_liquido for r in relatorios_grupo)
            total_valor_liquido += soma_grupo
            ids_grupo = [str(r.id) for r in relatorios_grupo]
            print(f"  Grupo ({forma_pagamento}, {bandeira}, {data_pagamento}, {maquinha}): {len(relatorios_grupo)} relatório(s) - IDs: {', '.join(ids_grupo)} - Soma: R$ {soma_grupo:.2f}")

        print(f"DEBUG CONCILIACAO: Valor líquido total de todos os relatórios selecionados: R$ {total_valor_liquido:.2f}")
        messages.info(request, f'Valor líquido total dos relatórios selecionados: R$ {total_valor_liquido:.2f}')

        # LOG ADICIONAL: Validar que combinações devem ser feitas apenas dentro do mesmo grupo
        print("\nDEBUG CONCILIACAO: VALIDAÇÃO DE GRUPOS - As combinações devem ser feitas APENAS dentro do mesmo grupo (mesma data_pagamento, forma_pagamento, bandeira, maquinha)")
        for chave, relatorios_grupo in grupos.items():
            forma_pagamento, bandeira, data_pagamento, maquinha = chave
            if len(relatorios_grupo) > 1:
                soma_grupo = sum(r.valor_liquido for r in relatorios_grupo)
                ids_grupo = [str(r.id) for r in relatorios_grupo]
                print(f"  GRUPO COM MÚLTIPLOS RELATÓRIOS: ({forma_pagamento}, {bandeira}, {data_pagamento}, {maquinha}) - IDs: {', '.join(ids_grupo)} - Soma do grupo: R$ {soma_grupo:.2f}")
                print("    -> Este grupo deve ser conciliado como uma unidade, não misturado com outros grupos!")

                # LOG DETALHADO: Mostrar valores individuais dos relatórios no grupo
                for r in relatorios_grupo:
                    print(f"      Relatório ID {r.id}: Valor líquido R$ {r.valor_liquido:.2f}")

        # LOG ESPECÍFICO: Verificar relatórios 1538, 1539, 1540, 1541 e 1542 especificamente
        ids_teste = [1538, 1539, 1540, 1541, 1542]
        relatorios_teste = relatorios.filter(id__in=ids_teste)
        if relatorios_teste.exists():
            print(f"\nDEBUG CONCILIACAO: VERIFICAÇÃO ESPECÍFICA DOS RELATÓRIOS {', '.join(map(str, ids_teste))}:")
            for r in relatorios_teste:
                print(f"  Relatório ID {r.id}: Data={r.data_pagamento}, Forma={r.forma_pagamento}, Bandeira={r.bandeira}, Maquinha={r.maquinha}, Valor=R$ {r.valor_liquido:.2f}")

            # Verificar grupos dos relatórios de teste
            grupos_teste = {}
            for r in relatorios_teste:
                chave = (r.forma_pagamento or 'N/A', r.bandeira or 'N/A', r.data_pagamento, r.maquinha or 'N/A')
                if chave not in grupos_teste:
                    grupos_teste[chave] = []
                grupos_teste[chave].append(r)

            print(f"\n  GRUPOS IDENTIFICADOS PARA OS RELATÓRIOS DE TESTE:")
            for chave, relatorios_grupo in grupos_teste.items():
                forma_pagamento, bandeira, data_pagamento, maquinha = chave
                soma_grupo = sum(r.valor_liquido for r in relatorios_grupo)
                ids_grupo = [str(r.id) for r in relatorios_grupo]
                print(f"    Grupo ({forma_pagamento}, {bandeira}, {data_pagamento}, {maquinha}): IDs {', '.join(ids_grupo)} - Soma: R$ {soma_grupo:.2f}")

            # Verificar se todos estão no mesmo grupo
            if len(grupos_teste) == 1:
                print("  -> OK: Todos os relatórios de teste estão no mesmo grupo e podem ser combinados.")
            else:
                print(f"  -> ALERTA: Os relatórios de teste estão em {len(grupos_teste)} grupos diferentes! Só podem ser combinados dentro do mesmo grupo.")

        # CORREÇÃO: Processar por grupos (mesma data_pagamento, forma_pagamento, bandeira, maquinha)
        conciliados = 0

        for chave_grupo, relatorios_grupo in grupos.items():
            forma_pagamento, bandeira, data_pagamento, maquinha = chave_grupo
            print(f"\nDEBUG CONCILIACAO: Processando grupo ({forma_pagamento}, {bandeira}, {data_pagamento}, {maquinha}) com {len(relatorios_grupo)} relatório(s)")

            # Buscar lançamentos não conciliados na mesma data ou próximos dias para este grupo
            lancamentos = Lancamento.objects.filter(
                empresa=empresa,
                data__range=(data_pagamento - timedelta(days=3), data_pagamento + timedelta(days=3)),
                conciliado=False
            )

            # Para SICOOB, filtrar lançamentos que contenham a forma_pagamento e bandeira no histórico
            if maquinha == 'SICOOB':
                lancamentos_filtrados = []
                for lancamento in lancamentos:
                    historico_lower = normalize_text(lancamento.historico or '')

                    # Verificar se o histórico contém a forma_pagamento e bandeira conforme especificação
                    forma_pagamento_lower = normalize_text(forma_pagamento or '')
                    bandeira_lower = normalize_text(bandeira or '')

                    # Determinar se é débito ou crédito
                    is_debito = 'debito' in forma_pagamento_lower or 'débito' in forma_pagamento_lower

                    # Construir o padrão esperado no histórico
                    if is_debito:
                        if bandeira_lower == 'visa':
                            expected_pattern = 'sipag_deb._visa'
                        elif bandeira_lower in ['mastercard', 'master']:
                            expected_pattern = 'sipag_deb._maestro'
                        elif bandeira_lower == 'elo':
                            expected_pattern = 'sipag_deb._elo'
                        else:
                            # Para outras bandeiras débito: SIPAG_Deb._Bandeira
                            expected_pattern = f'sipag_deb._{bandeira_lower}'
                    else:
                        # Crédito
                        if bandeira_lower == 'visa':
                            expected_pattern = 'sipag_cred._visa'
                        elif bandeira_lower == 'mastercard':
                            expected_pattern = 'sipag_cred._mastercard'
                        elif bandeira_lower == 'elo':
                            expected_pattern = 'sipag_cred._elo'
                        else:
                            # Para outras bandeiras crédito: SIPAG_Cred._Bandeira
                            expected_pattern = f'sipag_cred._{bandeira_lower}'

                    # Verificar se o padrão esperado está no histórico
                    if expected_pattern in historico_lower:
                        lancamentos_filtrados.append(lancamento)
                        print(f"DEBUG CONCILIACAO SICOOB: Lançamento {lancamento.id} corresponde ao padrão '{expected_pattern}'")

                lancamentos = lancamentos_filtrados
                print(f"DEBUG CONCILIACAO SICOOB: Após filtro por histórico, encontrados {len(lancamentos)} lançamentos válidos para grupo ({forma_pagamento}, {bandeira}, {data_pagamento}, {maquinha})")

            print(f"DEBUG CONCILIACAO: Encontrados {lancamentos.count()} lançamentos não conciliados no período para este grupo")
            for lanc in lancamentos:
                print(f"DEBUG CONCILIACAO: Lançamento ID {lanc.id} - Data: {lanc.data} - Valor: R$ {lanc.valor} - Histórico: {lanc.historico}")

            # Lista de relatórios deste grupo que ainda não foram conciliados
            relatorios_nao_conciliados_grupo = list(relatorios_grupo)

            while relatorios_nao_conciliados_grupo:
                relatorio = relatorios_nao_conciliados_grupo[0]  # Pegar primeiro relatório do grupo
                matching_lancamento = None
                relatorios_para_conciliar = [relatorio]  # Começar com apenas este relatório

                print(f"DEBUG CONCILIACAO: Processando relatório ID {relatorio.id} do grupo - Valor líquido: R$ {relatorio.valor_liquido}")

                # 1. Tentar encontrar correspondência exata por valor
                print(f"DEBUG CONCILIACAO: Procurando correspondência exata para relatório ID {relatorio.id} (Valor líquido: R$ {relatorio.valor_liquido:.2f})")
                for lancamento in lancamentos:
                    print(f"  Comparando com lançamento ID {lancamento.id}: R$ {lancamento.valor:.2f} (Diferença: R$ {abs(lancamento.valor - relatorio.valor_liquido):.2f})")
                    if abs(lancamento.valor - relatorio.valor_liquido) <= 0.10:  # Tolerância de 10 centavos
                        matching_lancamento = lancamento
                        print(f"  -> Correspondência exata encontrada: Lançamento ID {lancamento.id}")
                        break

                # 2. Se não encontrou correspondência exata, tentar combinações APENAS dentro do mesmo grupo
                if not matching_lancamento:
                    print(f"DEBUG CONCILIACAO: Não encontrou correspondência exata, tentando combinações dentro do grupo para relatório ID {relatorio.id}")
                    # Buscar outros relatórios não conciliados no mesmo grupo
                    outros_relatorios_grupo = [r for r in relatorios_nao_conciliados_grupo[1:] if r.id != relatorio.id]
                    print(f"DEBUG CONCILIACAO: Encontrados {len(outros_relatorios_grupo)} outros relatórios no mesmo grupo para combinação")

                    # PRIMEIRO: Tentar a combinação de TODOS os relatórios do grupo (quantidade que o usuário selecionou)
                    if outros_relatorios_grupo:  # Se há outros relatórios no grupo
                        combo_relatorios = [relatorio] + outros_relatorios_grupo
                        soma_valores = sum(r.valor_liquido for r in combo_relatorios)
                        combo_ids = [str(r.id) for r in combo_relatorios]

                        print(f"DEBUG CONCILIACAO: Testando combinação COMPLETA do grupo (IDs: {', '.join(combo_ids)}) - Soma: R$ {soma_valores:.2f}")

                        # Procurar lançamento que corresponda à soma total do grupo
                        for lancamento in lancamentos:
                            print(f"    Comparando soma total R$ {soma_valores:.2f} com lançamento ID {lancamento.id}: R$ {lancamento.valor:.2f} (Diferença: R$ {abs(lancamento.valor - soma_valores):.2f})")
                            if abs(lancamento.valor - soma_valores) <= 0.10:  # Tolerância de 10 centavos
                                matching_lancamento = lancamento
                                relatorios_para_conciliar = combo_relatorios
                                print(f"    -> Combinação COMPLETA do grupo encontrada! Lançamento ID {lancamento.id} corresponde à soma total dos relatórios {', '.join(combo_ids)}")
                                break
                        if matching_lancamento:
                            # Se encontrou combinação completa, usar ela
                            pass
                        else:
                            # Se não encontrou combinação completa, tentar combinações parciais de qualquer tamanho
                            print(f"DEBUG CONCILIACAO: Combinação completa não encontrada, tentando combinações parciais de qualquer tamanho...")

                    # Se ainda não encontrou, tentar TODAS as combinações possíveis dentro do grupo (de 2 até o tamanho máximo possível)
                    if not matching_lancamento:
                        # Tentar combinações do maior para o menor tamanho
                        max_combo_size = len(outros_relatorios_grupo) + 1  # +1 porque inclui o relatório atual
                        for num_relatorios in range(max_combo_size, 1, -1):  # De maior para menor, começando em max_combo_size até 2
                            from itertools import combinations
                            for combo in combinations(outros_relatorios_grupo, num_relatorios - 1):  # -1 porque inclui o relatório atual
                                combo_relatorios = [relatorio] + list(combo)
                                soma_valores = sum(r.valor_liquido for r in combo_relatorios)
                                combo_ids = [str(r.id) for r in combo_relatorios]

                                print(f"DEBUG CONCILIACAO: Testando combinação de {len(combo_relatorios)} relatórios do grupo (IDs: {', '.join(combo_ids)}) - Soma: R$ {soma_valores:.2f}")

                                # Procurar lançamento que corresponda à soma
                                for lancamento in lancamentos:
                                    print(f"    Comparando soma R$ {soma_valores:.2f} com lançamento ID {lancamento.id}: R$ {lancamento.valor:.2f} (Diferença: R$ {abs(lancamento.valor - soma_valores):.2f})")
                                    if abs(lancamento.valor - soma_valores) <= 0.10:  # Tolerância de 10 centavos
                                        matching_lancamento = lancamento
                                        relatorios_para_conciliar = combo_relatorios
                                        print(f"    -> Combinação encontrada dentro do grupo! Lançamento ID {lancamento.id} corresponde à soma dos relatórios {', '.join(combo_ids)}")
                                        break
                                if matching_lancamento:
                                    break
                            if matching_lancamento:
                                break

                if matching_lancamento:
                    # Usar transação atômica para garantir consistência
                    with transaction.atomic():
                        # Processar todos os relatórios da combinação
                        for idx, relatorio_atual in enumerate(relatorios_para_conciliar):
                            # 1. Buscar ou criar conta a receber para este relatório
                            conta = relatorio_atual.conta_a_receber

                            # Se não tem conta associada, tentar encontrar ou criar
                            if not conta:
                                from contasareceber.models import ContaAReceber

                                # Tentar encontrar conta baseada na nota fiscal
                                if relatorio_atual.nota_fiscal:
                                    from notasfiscais.models import NotaFiscalServico
                                    try:
                                        # CORREÇÃO: Usar .filter().first() ao invés de .get() para evitar DoesNotExist
                                        nota = NotaFiscalServico.objects.filter(
                                            empresa=empresa,
                                            numero_nota=relatorio_atual.nota_fiscal
                                        ).first()

                                        if nota:
                                            # Buscar conta a receber da nota
                                            conta = nota.contaareceber_set.first()
                                        else:
                                            # Se não encontrou exatamente, tentar busca mais flexível
                                            notas_similares = NotaFiscalServico.objects.filter(
                                                empresa=empresa,
                                                numero_nota__icontains=relatorio_atual.nota_fiscal.strip()
                                            )
                                            if notas_similares.exists():
                                                nota = notas_similares.first()
                                                conta = nota.contaareceber_set.first()
                                    except Exception as e:
                                        # Log do erro mas continua o processamento
                                        print(f"DEBUG CONCILIACAO: Erro ao buscar nota fiscal para relatório {relatorio_atual.id}: {str(e)}")
                                        pass

                                # Se ainda não encontrou, criar nova conta baseada nos dados do relatório
                                if not conta:
                                    # Parse data_emissao from data_venda if it's a string
                                    data_emissao_parsed = relatorio_atual.data_pagamento  # default fallback
                                    if relatorio_atual.data_venda:
                                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                                            try:
                                                data_emissao_parsed = datetime.strptime(relatorio_atual.data_venda, fmt).date()
                                                break
                                            except ValueError:
                                                continue

                                    # Determinar forma de pagamento baseada no relatório - buscar instância de Cobranca
                                    forma_pagamento_nome = 'CARTAO CREDITO'  # Default
                                    if relatorio_atual.forma_pagamento:
                                        forma_pagamento_lower = relatorio_atual.forma_pagamento.lower()
                                        if 'debito' in forma_pagamento_lower or 'débito' in forma_pagamento_lower:
                                            forma_pagamento_nome = 'CARTAO DEBITO'
                                        else:
                                            forma_pagamento_nome = 'CARTAO CREDITO'

                                    # Buscar instância de Cobranca correspondente
                                    from cobranca.models import Cobranca
                                    forma_pagamento_obj = Cobranca.objects.filter(descricao__iexact=forma_pagamento_nome).first()
                                    if not forma_pagamento_obj:
                                        # Se não encontrou, tentar buscar por descrição parcial
                                        forma_pagamento_obj = Cobranca.objects.filter(descricao__icontains=forma_pagamento_nome.split()[0]).first()
                                    if not forma_pagamento_obj:
                                        # Fallback: pegar primeira cobrança disponível
                                        forma_pagamento_obj = Cobranca.objects.first()

                                    conta = ContaAReceber.objects.create(
                                        empresa=empresa,
                                        cliente='CLIENTE DIVERSOS - CARTAO',
                                        valor_a_receber=relatorio_atual.valor_bruto,
                                        data_emissao=data_emissao_parsed,
                                        data_vencimento=relatorio_atual.data_pagamento,
                                        data_recebimento=relatorio_atual.data_pagamento,  # Data de recebimento = data de pagamento
                                        doc=relatorio_atual.nota_fiscal or f'Relatorio {relatorio_atual.id}',
                                        autorizacao=relatorio_atual.numero_autorizacao,
                                        forma_pagamento=forma_pagamento_obj,  # Usar instância de Cobranca
                                        valor_recebido=relatorio_atual.valor_liquido,  # Valor recebido = valor líquido
                                        juros=0,
                                        desconto=0,
                                        tarifas=relatorio_atual.taxa_maquinha or 0,  # Tarifas = taxa da máquina
                                        status='cartao',  # Definir status como cartão
                                        observacao=f'Relatório de recebíveis #{relatorio_atual.id} - {relatorio_atual.maquinha}'
                                    )
                                    messages.info(request, f'Conta a receber criada automaticamente para relatório {relatorio_atual.id}')
                                else:
                                    # Se encontrou conta existente (por autorização), apenas associar
                                    # NÃO alterar valores, status ou datas - isso será feito na conciliação com extrato
                                    messages.info(request, f'Conta a receber existente (cartão) associada ao relatório {relatorio_atual.id}')

                            # 2. Para contas criadas automaticamente ou existentes com status 'cartao', alterar para 'pago'
                            if conta.status == 'cartao':
                                conta.status = 'pago'
                                conta.save()
                                print(f"DEBUG CONCILIACAO: Conta a receber ID {conta.id} alterada de 'cartao' para 'pago'")

                            # 3. Lançar movimento no extrato bancário para cada relatório
                            from extrato.models import ExtratoMovimento

                            # Construir histórico conforme especificação
                            historico_parts = []
                            if matching_lancamento.historico:
                                historico_parts.append(matching_lancamento.historico)

                            # Adicionar nota fiscal
                            if conta and conta.nota:
                                historico_parts.append(f"NF {conta.nota.numero_nota}")
                            elif relatorio_atual.nota_fiscal:
                                historico_parts.append(f"NF {relatorio_atual.nota_fiscal}")

                            # Adicionar parcela
                            if relatorio_atual.parcelas and relatorio_atual.total_parcelas:
                                historico_parts.append(f"Parcela {relatorio_atual.parcelas}/{relatorio_atual.total_parcelas}")

                            # Adicionar razão
                            if relatorio_atual.razao:
                                historico_parts.append(relatorio_atual.razao)

                            # Adicionar valor do extrato bancário
                            historico_parts.append(f"R$ {matching_lancamento.valor}")

                            historico_completo = " - ".join(historico_parts)

                            ExtratoMovimento.objects.create(
                                empresa=empresa,
                                data_baixa=matching_lancamento.data,  # Data do extrato bancário
                                descricao=historico_completo,
                                situacao='recebido',
                                valor=relatorio_atual.valor_liquido,  # Valor do relatório
                                conta_receber=conta,
                                lancamento=matching_lancamento,
                                conta_banco=matching_lancamento.conta
                            )

                            # 4. Atualizar nota fiscal para conciliado
                            if conta and conta.nota:
                                conta.nota.status_conciliacao = 'conciliado'
                                conta.nota.save()

                            # 5. Atualizar relatório de recebíveis
                            relatorio_atual.conciliado = True
                            relatorio_atual.identificacao_extrato = f"{matching_lancamento.fitid} - {matching_lancamento.valor}"
                            relatorio_atual.conta_a_receber = conta  # Associar a conta encontrada/criada
                            # Formatar conta bancária apenas com agência e conta
                            conta_banco = matching_lancamento.conta
                            agencia_conta = f"{conta_banco.agencia}/{conta_banco.conta}" if conta_banco.agencia and conta_banco.conta else str(conta_banco)
                            relatorio_atual.conta_bancaria = agencia_conta
                            relatorio_atual.save()

                            # Remover este relatório da lista de não conciliados do grupo
                            if relatorio_atual in relatorios_nao_conciliados_grupo:
                                relatorios_nao_conciliados_grupo.remove(relatorio_atual)

                        # 6. Atualizar extrato bancário para conciliado (apenas uma vez)
                        matching_lancamento.conciliado = True
                        matching_lancamento.save()

                        conciliados += len(relatorios_para_conciliar)
                        if len(relatorios_para_conciliar) == 1:
                            messages.success(request, f'Relatório {relatorios_para_conciliar[0].id} conciliado com sucesso')
                        else:
                            relatorio_ids = [str(r.id) for r in relatorios_para_conciliar]
                            messages.success(request, f'Relatórios {", ".join(relatorio_ids)} conciliados com sucesso (R$ {matching_lancamento.valor})')
                else:
                    # Se não encontrou correspondência, remover este relatório da lista do grupo e continuar
                    relatorios_nao_conciliados_grupo.remove(relatorio)
                    messages.warning(request, f'Não foi encontrado lançamento correspondente para o relatório {relatorio.id}. Verifique se existe um lançamento bancário não conciliado com valor próximo a R$ {relatorio.valor_liquido:.2f} na data {relatorio.data_pagamento} ou próximos dias.')

        if conciliados > 0:
            messages.success(request, f'{conciliados} relatório(s) conciliado(s) com sucesso.')
        else:
            messages.warning(request, 'Nenhum relatório pôde ser conciliado.')

        return redirect('relatoriorecebiveis:relReclist')

    return redirect('relatoriorecebiveis:relReclist')
