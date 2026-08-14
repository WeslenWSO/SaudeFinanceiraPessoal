from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .forms import LoginForm


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