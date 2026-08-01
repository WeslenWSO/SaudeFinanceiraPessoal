"""Views Conta Azul — configuração por empresa, OAuth e sincronização."""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from dashboard.conta_azul.dashboards import montar_dashboard_por_tipo
from dashboard.conta_azul.resumo import montar_resumo_conta_azul
from dashboard.services.montar_visao_geral import REGIMES, montar_visao_geral
from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.config import gravar_tokens, limpar_tokens, obter_ou_criar_config
from dashboard.conta_azul.oauth import (
    BOOKMARKLET_CONTA_AZUL,
    ContaAzulOAuthError,
    extrair_parametros_oauth,
    gerar_state,
    trocar_codigo_por_tokens,
    url_autorizacao,
    validar_state_oauth,
)
from dashboard.conta_azul.sync import mensagem_resultado_sync, sincronizar_conta_azul
from dashboard.conta_azul_forms import ContaAzulConfigForm
from dashboard.models import ContaAzulConfig
from empresa.models import Empresa


def _empresa_autorizada(request, empresa: Empresa) -> bool:
    if request.user.is_superuser:
        return True
    sid = request.session.get('empresa_id')
    try:
        return int(sid) == int(empresa.pk)
    except (TypeError, ValueError):
        return str(sid) == str(empresa.pk)


@login_required
def conta_azul_config(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão para configurar esta empresa.')
        return redirect('empresa:lista')

    config = obter_ou_criar_config(empresa)

    if request.method == 'POST':
        form = ContaAzulConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuração Conta Azul salva.')
            return redirect('empresa:conta_azul_config', pk=pk)
        messages.error(request, 'Corrija os erros do formulário.')
    else:
        form = ContaAzulConfigForm(instance=config)

    return render(
        request,
        'empresa/conta_azul_config.html',
        {
            'empresa': empresa,
            'form': form,
            'config': config,
            'redirect_efetivo': config.redirect_uri_efetiva(),
            'url_oauth_preview': url_autorizacao(config, state='...') if config.credenciais_preenchidas() else '',
            'descricao': f'Conta Azul — {empresa.razao}',
        },
    )


def _conectar_com_codigo(request, empresa, config, code: str, *, state: str = '') -> bool:
    code = (code or '').strip()
    if not code:
        messages.error(request, 'Informe o código de autorização (parâmetro code= na URL).')
        return False
    if state and not validar_state_oauth(config, state):
        messages.error(
            request,
            'State OAuth não confere. Clique em Conectar novamente e use o código da autorização mais recente.',
        )
        return False
    try:
        payload = trocar_codigo_por_tokens(config, code=code)
        gravar_tokens(
            config,
            access_token=payload.get('access_token', ''),
            refresh_token=payload.get('refresh_token', ''),
            expires_in=int(payload.get('expires_in', 3600)),
        )
        config.oauth_state = ''
        config.save(update_fields=['oauth_state', 'atualizado_em'])
        messages.success(request, f'Conta Azul conectada para {empresa.razao}.')
        return True
    except (ContaAzulOAuthError, ContaAzulAPIError) as exc:
        messages.error(request, f'Erro ao conectar: {exc}')
        return False


@login_required
@require_POST
def conta_azul_trocar_codigo(request, pk):
    """Cole o code ou a URL completa após autorizar (fluxo DEV → redirect contaazul.com)."""
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão.')
        return redirect('empresa:lista')
    config = obter_ou_criar_config(empresa)
    bruto = (request.POST.get('authorization_code') or request.POST.get('oauth_callback') or '').strip()
    code, state = extrair_parametros_oauth(bruto)
    if _conectar_com_codigo(request, empresa, config, code, state=state):
        return redirect('empresa:conta_azul_config', pk=pk)
    if config.em_desenvolvimento():
        return redirect('empresa:conta_azul_oauth_dev', pk=pk)
    return redirect('empresa:conta_azul_config', pk=pk)


@login_required
@require_GET
def conta_azul_oauth_iniciar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão.')
        return redirect('empresa:lista')

    config = obter_ou_criar_config(empresa)
    if not config.credenciais_preenchidas():
        messages.error(request, 'Informe Client ID e Client Secret antes de conectar.')
        return redirect('empresa:conta_azul_config', pk=pk)

    state = gerar_state()
    config.oauth_state = state
    config.save(update_fields=['oauth_state', 'atualizado_em'])
    request.session['conta_azul_oauth_empresa_id'] = empresa.pk
    request.session['conta_azul_oauth_state'] = state

    if config.em_desenvolvimento():
        return redirect('empresa:conta_azul_oauth_dev', pk=pk)

    return redirect(url_autorizacao(config, state=state))


@login_required
def conta_azul_oauth_dev(request, pk):
    """Assistente OAuth para app Conta Azul em modo desenvolvimento (redirect → contaazul.com)."""
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão.')
        return redirect('empresa:lista')

    config = obter_ou_criar_config(empresa)
    if not config.em_desenvolvimento():
        return redirect('empresa:conta_azul_oauth_iniciar', pk=pk)
    if not config.credenciais_preenchidas():
        messages.error(request, 'Informe Client ID e Client Secret antes de conectar.')
        return redirect('empresa:conta_azul_config', pk=pk)

    if not (config.oauth_state or '').strip():
        state = gerar_state()
        config.oauth_state = state
        config.save(update_fields=['oauth_state', 'atualizado_em'])
        request.session['conta_azul_oauth_empresa_id'] = empresa.pk
        request.session['conta_azul_oauth_state'] = state

    state = config.oauth_state
    redirect_captura = config.redirect_uri_dev_captura(request.build_absolute_uri('/'))
    url_auth = url_autorizacao(config, state=state)
    url_auth_captura = url_autorizacao(config, state=state, redirect_uri=redirect_captura)

    if request.method == 'POST':
        bruto = (request.POST.get('oauth_callback') or '').strip()
        code, state_url = extrair_parametros_oauth(bruto)
        if _conectar_com_codigo(request, empresa, config, code, state=state_url):
            request.session.pop('conta_azul_oauth_state', None)
            request.session.pop('conta_azul_oauth_empresa_id', None)
            return redirect('empresa:conta_azul_config', pk=pk)
    else:
        bruto = ''

    return render(
        request,
        'empresa/conta_azul_oauth_dev.html',
        {
            'empresa': empresa,
            'config': config,
            'url_auth': url_auth,
            'url_auth_captura': url_auth_captura,
            'redirect_efetivo': config.redirect_uri_efetiva(),
            'redirect_captura': redirect_captura,
            'bookmarklet_href': BOOKMARKLET_CONTA_AZUL,
            'descricao': f'Conectar Conta Azul (DEV) — {empresa.razao}',
            'oauth_callback_valor': bruto,
            'empresa_pk': empresa.pk,
        },
    )


@require_GET
def conta_azul_oauth_dev_captura(request):
    """Página de retorno OAuth local — exibe popup com o code (cadastrar URL no portal Conta Azul)."""
    code = (request.GET.get('code') or '').strip()
    state = (request.GET.get('state') or '').strip()
    oauth_error = (request.GET.get('error') or '').strip()
    oauth_error_desc = (request.GET.get('error_description') or oauth_error).strip()
    empresa_id = request.session.get('conta_azul_oauth_empresa_id')
    return render(
        request,
        'empresa/conta_azul_oauth_dev_captura.html',
        {
            'code': code,
            'state': state,
            'oauth_error': oauth_error,
            'oauth_error_desc': oauth_error_desc,
            'empresa_id': empresa_id,
            'url_completa': request.build_absolute_uri(),
        },
    )


@login_required
@require_GET
def conta_azul_oauth_callback(request):
    oauth_error = (request.GET.get('error') or '').strip()
    if oauth_error:
        desc = (request.GET.get('error_description') or oauth_error).strip()
        empresa_id = request.session.get('conta_azul_oauth_empresa_id')
        if oauth_error == 'redirect_mismatch':
            messages.error(
                request,
                'Redirect URI não confere com o cadastro no Portal Conta Azul. '
                'Copie o "Redirect em uso" desta tela e cadastre exatamente igual no portal, '
                'depois salve e clique em Reconectar.',
            )
        else:
            messages.error(request, f'Autorização recusada: {desc}')
        request.session.pop('conta_azul_oauth_state', None)
        if empresa_id:
            return redirect('empresa:conta_azul_config', pk=empresa_id)
        return redirect('empresa:lista')

    code = (request.GET.get('code') or '').strip()
    state = (request.GET.get('state') or '').strip()
    sess_state = (request.session.get('conta_azul_oauth_state') or '').strip()
    empresa_id = request.session.get('conta_azul_oauth_empresa_id')

    if not code or not state or state != sess_state or not empresa_id:
        messages.error(request, 'Autorização inválida ou expirada. Tente conectar novamente.')
        return redirect('empresa:lista')

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    config = obter_ou_criar_config(empresa)

    try:
        if _conectar_com_codigo(request, empresa, config, code, state=state):
            pass
    finally:
        request.session.pop('conta_azul_oauth_state', None)
        request.session.pop('conta_azul_oauth_empresa_id', None)
    return redirect('empresa:conta_azul_config', pk=empresa_id)


@login_required
@require_POST
def conta_azul_desconectar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão.')
        return redirect('empresa:lista')
    try:
        config = empresa.conta_azul_config
        limpar_tokens(config)
        messages.info(request, 'Conta Azul desconectada (credenciais mantidas).')
    except ContaAzulConfig.DoesNotExist:
        pass
    return redirect('empresa:conta_azul_config', pk=pk)


@login_required
@require_POST
def conta_azul_testar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão.')
        return redirect('empresa:lista')
    try:
        client = ContaAzulClient.para_empresa(empresa)
        client.testar_conexao()
        messages.success(request, 'Conexão com a API Conta Azul OK.')
    except ContaAzulAPIError as exc:
        messages.error(request, f'Falha no teste: {exc}')
    return redirect('empresa:conta_azul_config', pk=pk)


@login_required
def conta_azul_sincronizar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    if not _empresa_autorizada(request, empresa):
        messages.error(request, 'Sem permissão.')
        return redirect('empresa:lista')

    hoje = date.today()
    config = obter_ou_criar_config(empresa)
    if request.method == 'POST':
        if not config.tem_refresh_token():
            messages.error(
                request,
                'Conta Azul ainda não está conectada (OAuth). '
                'Abra a configuração, clique em Conectar/Reconectar ou cole o código manual.',
            )
            return redirect('empresa:conta_azul_config', pk=pk)
        try:
            ano = int(request.POST.get('ano') or hoje.year)
            mes = int(request.POST.get('mes') or hoje.month)
        except (TypeError, ValueError):
            ano, mes = hoje.year, hoje.month
        data_de = date(ano, mes, 1)
        if mes == 12:
            data_ate = date(ano, 12, 31)
        else:
            data_ate = date(ano, mes + 1, 1)
            from datetime import timedelta
            data_ate = data_ate - timedelta(days=1)

        try:
            stats = sincronizar_conta_azul(
                empresa,
                cadastros='cadastros' in request.POST,
                receitas='receitas' in request.POST,
                despesas='despesas' in request.POST,
                transferencias='transferencias' in request.POST,
                data_de=data_de,
                data_ate=data_ate,
            )
            nivel, texto = mensagem_resultado_sync(stats)
            getattr(messages, nivel)(request, texto)
        except IntegrityError as exc:
            messages.error(
                request,
                f'Conflito ao gravar dados (conta/categoria duplicada). '
                f'Detalhe: {exc}. Tente sincronizar só cadastros primeiro.',
            )
        except ContaAzulAPIError as exc:
            messages.error(request, f'Erro na sincronização: {exc}')
        return redirect('empresa:conta_azul_sincronizar', pk=pk)

    return render(
        request,
        'empresa/conta_azul_sincronizar.html',
        {
            'empresa': empresa,
            'config': config,
            'descricao': f'Sincronizar Conta Azul — {empresa.razao}',
            'mes_ref': hoje.month,
            'ano_ref': hoje.year,
        },
    )


@login_required
@require_POST
def conta_azul_sincronizar_dashboard(request):
    from datetime import timedelta

    from django.shortcuts import redirect as rd

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Selecione uma empresa.')
        return rd('empresa:lista')
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    config = obter_ou_criar_config(empresa)
    if not config.tem_refresh_token():
        messages.error(
            request,
            'Conta Azul não conectada. Configure OAuth antes de sincronizar.',
        )
        return rd('empresa:conta_azul_config', pk=empresa_id)
    mes = int(request.GET.get('mes') or request.POST.get('mes') or date.today().month)
    ano = int(request.GET.get('ano') or request.POST.get('ano') or date.today().year)
    data_de = date(ano, mes, 1)
    if mes == 12:
        data_ate = date(ano, 12, 31)
    else:
        data_ate = date(ano, mes + 1, 1) - timedelta(days=1)
    try:
        stats = sincronizar_conta_azul(
            empresa,
            cadastros=True,
            receitas=True,
            despesas=True,
            transferencias=False,
            data_de=data_de,
            data_ate=data_ate,
        )
        nivel, texto = mensagem_resultado_sync(stats)
        getattr(messages, nivel)(request, texto)
    except ContaAzulAPIError as exc:
        messages.error(request, f'Erro: {exc}')
    from django.urls import reverse

    return rd(reverse('dashboard:index') + f'?mes={mes}&ano={ano}')


MESES_PT = (
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
)


def _contexto_dashboard_mensal(request):
    """Empresa da sessão + filtro mês/ano compartilhado pelos dashboards CA."""
    from calendar import monthrange

    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return None, None

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    hoje = date.today()
    try:
        ano_ref = int(request.GET.get('ano') or hoje.year)
        mes_ref = int(request.GET.get('mes') or hoje.month)
    except (TypeError, ValueError):
        ano_ref, mes_ref = hoje.year, hoje.month
    if mes_ref < 1 or mes_ref > 12:
        mes_ref = hoje.month
    if ano_ref < 2000 or ano_ref > 2100:
        ano_ref = hoje.year

    primeiro_mes = date(ano_ref, mes_ref, 1)
    ultimo_mes = date(ano_ref, mes_ref, monthrange(ano_ref, mes_ref)[1])
    titulo_mes = f'{MESES_PT[mes_ref - 1]} de {ano_ref}'
    meses_opcoes = list(enumerate(MESES_PT, start=1))

    ctx = {
        'empresa': empresa,
        'titulo_mes': titulo_mes,
        'mes_ref': mes_ref,
        'ano_ref': ano_ref,
        'meses_opcoes': meses_opcoes,
        'primeiro_mes': primeiro_mes,
        'ultimo_mes': ultimo_mes,
    }
    return empresa, ctx


def _parse_data_param(valor, fallback: date) -> date:
    if not valor:
        return fallback
    try:
        partes = str(valor).strip().split('-')
        if len(partes) == 3:
            return date(int(partes[0]), int(partes[1]), int(partes[2]))
    except (TypeError, ValueError):
        pass
    return fallback


def _contexto_dashboard_intervalo(request):
    """Empresa da sessão + intervalo de datas + regime (Visão Geral / Competência / Caixa)."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return None, None

    empresa = get_object_or_404(Empresa, pk=empresa_id)
    hoje = date.today()
    ano_atual = hoje.year

    data_inicio = _parse_data_param(
        request.GET.get('data_inicio'),
        date(ano_atual, 1, 1),
    )
    data_fim = _parse_data_param(
        request.GET.get('data_fim'),
        date(ano_atual, 12, 31),
    )
    if data_fim < data_inicio:
        data_inicio, data_fim = data_fim, data_inicio

    regime = (request.GET.get('regime') or 'geral').strip().lower()
    if regime not in {r[0] for r in REGIMES}:
        regime = 'geral'

    titulo_periodo = (
        f'{data_inicio.strftime("%d/%m/%Y")} — {data_fim.strftime("%d/%m/%Y")}'
    )

    ctx = {
        'empresa': empresa,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'data_inicio_str': data_inicio.isoformat(),
        'data_fim_str': data_fim.isoformat(),
        'regime': regime,
        'regimes': REGIMES,
        'titulo_periodo': titulo_periodo,
    }
    return empresa, ctx


@login_required
def conta_azul_dashboard(request):
    """Dashboard principal — Visão Geral com gráficos financeiros."""
    empresa, ctx = _contexto_dashboard_intervalo(request)
    if not empresa:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')

    visao = montar_visao_geral(empresa, ctx['data_inicio'], ctx['data_fim'], ctx['regime'])
    return render(
        request,
        'dashboard/conta_azul_dashboard.html',
        {
            'titulo': 'Dashboard',
            'visao': visao,
            'dashboard_ativo': 'geral',
            **ctx,
        },
    )


@login_required
def conta_azul_dashboard_por_tipo(request):
    empresa, ctx = _contexto_dashboard_mensal(request)
    if not empresa:
        messages.error(request, 'Selecione uma empresa.')
        return redirect('empresa:lista')

    dados = montar_dashboard_por_tipo(empresa, ctx['primeiro_mes'], ctx['ultimo_mes'])
    return render(
        request,
        'dashboard/conta_azul_por_tipo.html',
        {'dados': dados, 'dashboard_ativo': 'por_tipo', **ctx},
    )
