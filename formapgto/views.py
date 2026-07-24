# FormaPgto foi removido; usar cobranca.Cobranca.
# Estas views redirecionam para a app cobranca.

from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic.base import RedirectView


class FormaPgtoList(RedirectView):
    """Redireciona lista de forma de pagto para lista de Cobrança."""
    url = reverse_lazy('cobranca:cobList')
    permanent = False


class FormaDetail(RedirectView):
    """Redireciona detalhe para lista de Cobrança."""
    url = reverse_lazy('cobranca:cobList')
    permanent = False


class FormaUpdate(RedirectView):
    """Redireciona edição para lista de Cobrança (editar em cobranca)."""
    url = reverse_lazy('cobranca:cobList')
    permanent = False


class FormaCreate(RedirectView):
    """Redireciona criação para nova Cobrança."""
    url = reverse_lazy('cobranca:cob-create')
    permanent = False
