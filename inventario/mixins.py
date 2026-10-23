from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect

from inventario.permissoes import usuario_pode_inventario


class RequerAdminInventarioMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return usuario_pode_inventario(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, 'Inventário de estoque: somente administradores.')
            return redirect('estoque:farmacia_list')
        return super().handle_no_permission()
