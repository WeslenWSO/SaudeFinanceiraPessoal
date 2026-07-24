#!/usr/bin/env python
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from notasfiscais.models import NotaFiscalServico

print('Total de notas:', NotaFiscalServico.objects.count())
if NotaFiscalServico.objects.exists():
    nota = NotaFiscalServico.objects.first()
    print('Primeira nota ID:', nota.id, 'Numero:', nota.numero_nota)
else:
    print('Nenhuma nota encontrada')