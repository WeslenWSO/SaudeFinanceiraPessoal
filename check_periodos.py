#!/usr/bin/env python
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from notasfiscais.models import ApuracaoPeriodo
from empresa.models import Empresa

print('Períodos fechados:')
periodos_fechados = ApuracaoPeriodo.objects.filter(status='fechado').select_related('empresa')
for p in periodos_fechados:
    print(f'- Empresa: {p.empresa.razao}, Período: {p.data_inicio} a {p.data_fim}, Status: {p.status}')

print('\nTodos os períodos:')
todos_periodos = ApuracaoPeriodo.objects.all().select_related('empresa')
for p in todos_periodos:
    print(f'- Empresa: {p.empresa.razao}, Período: {p.data_inicio} a {p.data_fim}, Status: {p.status}')