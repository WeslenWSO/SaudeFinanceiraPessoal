"""
WSGI config for SaudeFinanceira project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

# Compatibilidade: alguns ambientes (ex.: servidor com pacotes mistos) tentam
# importar lazy_annotations de django.utils.inspect, que só existe no Django 5.2+.
# Em Django 4.2 esse nome não existe e gera ImportError/500. Adicionamos um stub se faltar.
import django.utils.inspect as _django_inspect
if not hasattr(_django_inspect, 'lazy_annotations'):
    def _lazy_annotations(func):
        return func
    _django_inspect.lazy_annotations = _lazy_annotations

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
