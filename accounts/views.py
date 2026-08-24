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
            return redirect('accounts:backup_banco')

        if not request.user.check_password(senha):
            messages.error(request, 'Senha incorreta.')
            return redirect('accounts:backup_banco')

        try:
            info = criar_backup_completo()
        except Exception as exc:
            messages.error(request, f'Erro ao gerar backup: {exc}')
            return redirect('accounts:backup_banco')

        caminho = caminho_backup_seguro(info['arquivo'])
        if not caminho:
            messages.error(request, 'Backup gerado, mas o arquivo não foi encontrado.')
            return redirect('accounts:backup_banco')

        messages.success(
            request,
            f'Backup salvo em {caminho} ({_formatar_tamanho(info["tamanho"])}).',
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

    context = {
        'pasta_backups': str(diretorio_backups()),
        'backups_locais': backups,
        'usa_pg_dump': _engine_postgres() and bool(_pg_dump_disponivel()),
    }
    return render(request, 'accounts/backup_banco.html', context)


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