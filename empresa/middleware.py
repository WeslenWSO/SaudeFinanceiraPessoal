from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages

class EmpresaMiddleware:
    """Middleware para verificar se o usuário tem empresa selecionada"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # URLs que não precisam de empresa selecionada
        exempt_urls = [
            '/admin/',
            '/accounts/',
            '/empresa/lista/',
            '/empresa/selecionar/',
            '/empresa/trocar/',
            '/empresa/atual/',
        ]
        
        # Verifica se a URL atual está na lista de exceções
        is_exempt = any(request.path.startswith(url) for url in exempt_urls)
        
        # Se o usuário está logado e não é uma URL exceção
        if request.user.is_authenticated and not is_exempt:
            empresa_id = request.session.get('empresa_id')
            
            # Se não tem empresa selecionada, redireciona para seleção
            if not empresa_id:
                messages.warning(request, 'Selecione uma empresa para continuar.')
                return redirect('empresa:lista')
        
        response = self.get_response(request)
        return response
