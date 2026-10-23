from django.urls import reverse


def alertas_estoque_minimo(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    empresa_id = request.session.get('empresa_id')
    try:
        from estoque.alertas import contar_abaixo_estoque_minimo
        from usuario.menu import usuario_pode_menu

        if not empresa_id or not usuario_pode_menu(request.user, 'estoque_farmacia'):
            return {
                'estoque_alertas_abaixo_minimo': 0,
                'estoque_alertas_url': '',
            }
        n = contar_abaixo_estoque_minimo(empresa_id)
        url = ''
        if n:
            url = reverse('estoque:farmacia_list') + '?somente_alertas=1'
        return {
            'estoque_alertas_abaixo_minimo': n,
            'estoque_alertas_url': url,
        }
    except Exception:
        return {'estoque_alertas_abaixo_minimo': 0, 'estoque_alertas_url': ''}
