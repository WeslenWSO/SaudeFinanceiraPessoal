# notasfiscais/middleware.py
"""
Middleware que limpa os filtros persistidos da listagem NFSe quando o usuário
sai do módulo (ex.: clicando em outro item do menu lateral).
"""
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.contrib.sessions.exceptions import SessionInterrupted

# Prefixos de path que identificam o módulo NFSe (ajuste se criar nova rota).
# No urls.py: path('notasfiscais/', ...) e path('nfse/', ...)
NFS_PATH_PREFIXES = ('/notasfiscais/', '/nfse/')
NFS_SESSION_KEY = 'nfs_filtros'
LAST_PATH_SESSION_KEY = '_nfs_last_path'

# Paths ignorados (não contam como "saída" do módulo)
IGNORE_PREFIXES = ('/static/', '/media/', '/admin/', '/favicon.ico')


def _is_nfs_path(path: str) -> bool:
    """Verifica se path pertence ao módulo NFSe."""
    if not path:
        return False
    return any(path.startswith(prefix) for prefix in NFS_PATH_PREFIXES)


def _should_ignore(path: str) -> bool:
    """Ignora assets e admin."""
    return any(path.startswith(p) for p in IGNORE_PREFIXES)


class ClearNFSeFiltersOnLeaveMiddleware(MiddlewareMixin):
    """
    Após processar a request, atualiza _nfs_last_path.
    Se o last_path era NFSe e o path atual NÃO é NFSe, remove nfs_filtros da session.
    """

    def process_response(self, request, response):
        if not hasattr(request, 'session'):
            return response
        path = request.path
        if _should_ignore(path):
            return response
        last = request.session.get(LAST_PATH_SESSION_KEY)
        request.session[LAST_PATH_SESSION_KEY] = path
        if last and _is_nfs_path(last) and not _is_nfs_path(path):
            request.session.pop(NFS_SESSION_KEY, None)
        return response


class HandleSessionInterruptedMiddleware:
    """Redireciona para o login quando a sessão foi encerrada durante a requisição."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except SessionInterrupted:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse(
                    {'erro': 'Sessão expirada. Faça login novamente e tente de novo.'},
                    status=401,
                )
            return redirect('/login/')
