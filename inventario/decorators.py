from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from inventario.permissoes import usuario_pode_inventario


def admin_inventario_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not usuario_pode_inventario(request.user):
            messages.error(request, 'Inventário de estoque: somente administradores.')
            return redirect('estoque:farmacia_list')
        return view_func(request, *args, **kwargs)

    return _wrapped
