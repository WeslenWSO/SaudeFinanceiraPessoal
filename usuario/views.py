from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView, CreateView

from usuario.models import Usuario
from usuario.forms import UsuarioForm
from usuario.auth_sync import sincronizar_login_usuario
from usuario.permissoes_menu import salvar_permissoes_menu


def _permissoes_menu_do_post(form, request):
    if 'permissoes_menu' in form.cleaned_data:
        return form.cleaned_data['permissoes_menu']
    if request.method == 'POST':
        return request.POST.getlist('permissoes_menu')
    return None

# Create your views here.
def listaUsuario(request):
    print(request.POST)
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        usuarios = Usuario.objects.filter(empresa_id=empresa_id)
    else:
        usuarios = Usuario.objects.all()
   
    
    
     

    page = request.GET.get('p')
    # socios = paginator.get_page(page)
    return render(request, 'usuarioList.html', {'usuarios': usuarios


    })

class UsuarioCreate(CreateView):
    model = Usuario
    form_class = UsuarioForm
    template_name = 'usuario-add-alterar.html'
    success_url = reverse_lazy('usuario:usuarioList')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Usuário'
        context["titulo"] = 'Usuário'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        auth_user = sincronizar_login_usuario(self.object, form.cleaned_data['senha'])
        codigos = _permissoes_menu_do_post(form, self.request)
        if codigos is not None:
            salvar_permissoes_menu(self.object, codigos, user=auth_user)
        messages.success(
            self.request,
            f'Usuario "{self.object.usuario}" salvo. Login liberado em /login/.'
            + (f' Permissoes de menu: {len(codigos)}.' if codigos is not None else ''),
        )
        return response


class UsuarioUpdate(UpdateView):
    model = Usuario
    form_class = UsuarioForm
    template_name = 'usuario-add-alterar.html'
    success_url = reverse_lazy('usuario:usuarioList')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Usuário'
        context["titulo"] = 'Usuário'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        senha = form.cleaned_data.get('senha') or None
        auth_user = sincronizar_login_usuario(self.object, senha)
        codigos = _permissoes_menu_do_post(form, self.request)
        if codigos is not None:
            salvar_permissoes_menu(self.object, codigos, user=auth_user)
        msg = f'Usuario "{self.object.usuario}" atualizado.'
        if codigos is not None:
            msg += f' Permissoes de menu: {len(codigos)}.'
        messages.success(self.request, msg)
        return response