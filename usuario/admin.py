from django.contrib import admin, messages

from .forms import UsuarioForm
from .models import PermissaoMenuUsuario, Usuario
from .auth_sync import sincronizar_login_usuario
from .permissoes_menu import salvar_permissoes_menu


class PermissaoMenuUsuarioInline(admin.TabularInline):
    model = PermissaoMenuUsuario
    extra = 0
    fields = ('codigo',)


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    form = UsuarioForm
    list_display = ('id', 'usuario', 'lastname', 'email', 'empresa')
    list_display_links = ('id', 'usuario')
    list_filter = ('empresa',)
    search_fields = ('usuario', 'lastname', 'email')
    list_per_page = 20

    fieldsets = (
        (
            None,
            {
                'fields': ('empresa', 'usuario', 'lastname', 'email', 'avatar'),
            },
        ),
        (
            'Login do sistema',
            {
                'fields': ('senha', 'confirmar_senha'),
                'description': (
                    'Estes campos criam o login em /login/ (auth.User). '
                    'Na edicao, deixe a senha em branco para nao alterar.'
                ),
            },
        ),
        (
            'Permissões do menu',
            {
                'fields': ('permissoes_menu',),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        senha = form.cleaned_data.get('senha') or None
        try:
            auth_user = sincronizar_login_usuario(obj, senha)
        except Exception as exc:
            messages.error(request, f'Erro ao sincronizar login: {exc}')
            return
        codigos = form.cleaned_data.get('permissoes_menu')
        if codigos is None and hasattr(request.POST, 'getlist'):
            codigos = request.POST.getlist('permissoes_menu')
        if auth_user is None:
            messages.error(
                request,
                'Login nao sincronizado. Permissoes de menu nao foram salvas.',
            )
            return
        try:
            salvar_permissoes_menu(obj, codigos or [], user=auth_user)
            messages.info(
                request,
                f'Permissoes de menu salvas: {len(codigos or [])} item(ns).',
            )
        except Exception as exc:
            messages.error(request, f'Erro ao salvar permissoes de menu: {exc}')


@admin.register(PermissaoMenuUsuario)
class PermissaoMenuUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'codigo')
    list_filter = ('codigo',)
    search_fields = ('usuario__username', 'codigo')
