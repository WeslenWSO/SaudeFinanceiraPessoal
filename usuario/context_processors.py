def menu_nav(request):
    from usuario.menu import montar_menu_nav

    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    try:
        return {'menu_nav': montar_menu_nav(user)}
    except Exception:
        return {'menu_nav': {'links': [], 'dropdowns': []}}
