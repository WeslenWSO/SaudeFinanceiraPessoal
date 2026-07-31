from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def montar_menu_nav_tag(context):
    from usuario.menu import montar_menu_nav

    request = context.get('request')
    user = None
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        user = request.user
    return montar_menu_nav(user)
