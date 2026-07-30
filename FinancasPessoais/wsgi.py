"""
Compatibilidade com o start command antigo no Render:
gunicorn FinancasPessoais.wsgi:application
"""
from SaudeFinanceira.wsgi import application

__all__ = ['application']
