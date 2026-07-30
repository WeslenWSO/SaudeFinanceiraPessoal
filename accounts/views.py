from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from empresa.models import UsuarioEmpresa
from .forms import LoginForm


def _selecionar_empresa_unica(request, user):
    usuario_empresas = UsuarioEmpresa.objects.filter(
        usuario=user,
        ativo=True,
        empresa__status='Ativa',
    ).select_related('empresa')
    if usuario_empresas.count() != 1:
        return None
    empresa = usuario_empresas.first().empresa
    request.session['empresa_id'] = empresa.id
    request.session['empresa_nome'] = empresa.razao
    request.session['regime_tributario'] = empresa.regime_tributario
    return empresa


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        
        if form.is_valid():
            username = form.cleaned_data['username'].strip()
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                if _selecionar_empresa_unica(request, user):
                    return redirect('dashboard:index')
                return redirect('empresa:lista')
            else:
                form.add_error(None, 'Usuário ou senha incorretos.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('accounts:login')  # Redirecionar para a página de login