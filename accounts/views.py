from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods

from .forms import LoginForm
from .backup_banco import (
    criar_backup_completo,
    listar_backups_locais,
    caminho_backup_seguro,
    diretorio_backups,
    _engine_postgres,
    _pg_dump_disponivel,
)


def _usuario_admin(user):
    return user.is_authenticated and user.is_superuser


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username'].strip()
            password = form.cleaned_data['password'].strip()
            from django.contrib.auth.models import User

            db_user = User.objects.filter(username__iexact=username).first()
            auth_username = db_user.username if db_user else username
            user = authenticate(request, username=auth_username, password=password)

            if user is not None:
                login(request, user)
                for key in ('empresa_id', 'empresa_nome', 'regime_tributario'):
                    request.session.pop(key, None)
                from agendador_tarefas.letreiro import marcar_popup_tarefas_letreiro

                marcar_popup_tarefas_letreiro(request)
                return redirect('empresa:lista')
            else:
                form.add_error(None, 'Usuário ou senha incorretos.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('accounts:login')  # Redirecionar para a página de login


def _formatar_tamanho(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f'{num_bytes} B'
    if num_bytes < 1024 * 1024:
        return f'{num_bytes / 1024:.1f} KB'
    return f'{num_bytes / (1024 * 1024):.1f} MB'


@login_required
@user_passes_test(_usuario_admin)
@require_http_methods(['GET', 'POST'])
def backup_banco_view(request):
    """Gera backup completo do banco (somente superuser + confirmação de senha)."""
    if request.method == 'POST':
        senha = (request.POST.get('senha') or '').strip()
        if not senha:
            messages.error(request, 'Informe sua senha para confirmar o backup.')
            return redirect('backup_banco')

        if not request.user.check_password(senha):
            messages.error(request, 'Senha incorreta.')
            return redirect('backup_banco')

        try:
            info = criar_backup_completo()
        except Exception as exc:
            messages.error(request, f'Erro ao gerar backup: {exc}')
            return redirect('backup_banco')

        caminho = caminho_backup_seguro(info['arquivo'])
        if not caminho:
            messages.error(request, 'Backup gerado, mas o arquivo não foi encontrado.')
            return redirect('backup_banco')

        msg = f'Backup salvo em {caminho} ({_formatar_tamanho(info["tamanho"])}).'
        from accounts.backup_google_drive import drive_configurado, enviar_backup_info_para_drive

        if drive_configurado():
            try:
                ups = enviar_backup_info_para_drive(info)
                msg += (
                    f' Enviado ao Google Drive (BKP_SAUDE): '
                    f'{", ".join(u.get("name", "") for u in ups)}. '
                    f'Cópia local será mantida por 5 dias.'
                )
                messages.success(request, msg)
            except Exception as exc:
                messages.error(request, f'{msg} Não enviou ao Drive — {exc}')
        else:
            messages.warning(
                request,
                msg
                + ' Drive não configurado neste servidor (BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON).',
            )

        content_type = 'application/gzip' if info['formato'] == 'sql.gz' else 'application/json'
        response = FileResponse(caminho.open('rb'), as_attachment=True, filename=info['arquivo'])
        response['Content-Type'] = content_type
        return response

    backups = []
    for item in listar_backups_locais():
        backups.append({
            **item,
            'tamanho_fmt': _formatar_tamanho(item['tamanho']),
        })

    from accounts.backup_config import horarios_backup_ativos, obter_config_backup
    from accounts.backup_google_drive import drive_configurado

    cfg = obter_config_backup()
    context = {
        'pasta_backups': str(diretorio_backups()),
        'backups_locais': backups,
        'usa_pg_dump': _engine_postgres() and bool(_pg_dump_disponivel()),
        'drive_backup_configurado': drive_configurado(),
        'backup_cfg': cfg,
        'backup_horarios': horarios_backup_ativos(cfg),
    }
    return render(request, 'accounts/backup_banco.html', context)


@login_required
@user_passes_test(_usuario_admin)
@require_http_methods(['GET', 'POST'])
def backup_agendamento_config_view(request):
    """Horários, pasta Drive e sincronização de tarefas no agendador."""
    from accounts.backup_config import horarios_backup_ativos, obter_config_backup
    from accounts.forms_backup import BackupBancoConfigForm
    from agendador_tarefas.seed_backup_banco import sincronizar_tarefas_backup_banco_agenda

    config = obter_config_backup()

    if request.method == 'POST':
        acao = (request.POST.get('acao') or 'salvar').strip()
        if acao == 'sincronizar_tarefas':
            n = sincronizar_tarefas_backup_banco_agenda()
            messages.success(
                request,
                f'Tarefas de backup recriadas no agendador ({n} novas entradas).',
            )
            return redirect('backup_agendamento_config')

        if acao == 'executar_backup_agora':
            from accounts.backup_runner import executar_backup_google_drive

            try:
                result = executar_backup_google_drive(modo='manual')
            except Exception as exc:
                messages.error(request, f'Erro ao executar backup: {exc}')
                return redirect('backup_agendamento_config')
            if result.get('pulou'):
                messages.warning(request, result.get('mensagem', 'Nada executado.'))
            elif result.get('ok'):
                messages.success(request, result.get('mensagem', 'Backup enviado ao Drive.'))
            else:
                messages.warning(
                    request,
                    result.get('mensagem', 'Backup local OK; Drive não configurado neste servidor.'),
                )
            return redirect('backup_agendamento_config')

        form = BackupBancoConfigForm(request.POST, instance=config)
        if form.is_valid():
            cfg = form.save()
            if cfg.gerar_tarefas_agendador:
                n = sincronizar_tarefas_backup_banco_agenda()
                messages.success(
                    request,
                    f'Configuração salva. Tarefas no agendador atualizadas ({n} criadas).',
                )
            else:
                from agendador_tarefas.seed_backup_banco import remover_tarefas_backup_banco_agenda
                from agendador_tarefas.models import TarefaAgendada

                remover_tarefas_backup_banco_agenda(TarefaAgendada)
                messages.success(
                    request,
                    'Configuração salva. Lembretes de backup removidos do agendador.',
                )
            return redirect('backup_agendamento_config')
    else:
        form = BackupBancoConfigForm(instance=config)

    from accounts.backup_google_drive import drive_configurado, email_service_account_drive
    from accounts.models import BackupExecucaoAgendada

    ultimas_execucoes = list(
        BackupExecucaoAgendada.objects.order_by('-executado_em')[:15]
    )

    return render(
        request,
        'accounts/backup_agendamento_config.html',
        {
            'form': form,
            'horarios_ativos': horarios_backup_ativos(config),
            'drive_credencial_ok': drive_configurado(),
            'drive_service_account_email': email_service_account_drive(),
            'ultimas_execucoes': ultimas_execucoes,
        },
    )


@login_required
@user_passes_test(_usuario_admin)
def backup_banco_download(request, nome):
    """Download de backup já existente na pasta local."""
    caminho = caminho_backup_seguro(nome)
    if not caminho:
        raise Http404('Arquivo não encontrado.')
    if nome.endswith('.gz'):
        content_type = 'application/gzip'
    elif nome.endswith('.json'):
        content_type = 'application/json'
    else:
        content_type = 'application/octet-stream'
    response = FileResponse(caminho.open('rb'), as_attachment=True, filename=nome)
    response['Content-Type'] = content_type
    return response