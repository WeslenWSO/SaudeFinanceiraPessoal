from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .forms import LoginForm


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                #return redirect('dashboard')  # Redirecionar para uma página inicial, por exemplo
                #auth.login(request, user)
                
                return redirect('empresa:lista')
            else:
                form.add_error(None, "Username or password is incorrect")
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('accounts:login')  # Redirecionar para a página de login