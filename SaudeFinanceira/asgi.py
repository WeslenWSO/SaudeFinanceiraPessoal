"""
ASGI config for SaudeFinanceira project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

from django.core.asgi import get_asgi_application

application = get_asgi_application()
