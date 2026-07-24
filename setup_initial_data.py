#!/usr/bin/env python
import os
import sys
import django

# Configurar o Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from empresa.models import Empresa, UsuarioEmpresa
from django.contrib.auth.models import User

def setup_initial_data():
    print("Configurando dados iniciais...")
    
    # Verificar se já existe um superusuário
    try:
        user = User.objects.get(username='admin')
        print(f'Usuário admin já existe: {user.username}')
    except User.DoesNotExist:
        user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
        print(f'Usuário admin criado: {user.username}')
    
    # Verificar se já existe uma empresa
    try:
        empresa = Empresa.objects.get(cnpj='12345678000199')
        print(f'Empresa já existe: {empresa.razao}')
    except Empresa.DoesNotExist:
        empresa = Empresa.objects.create(
            razao='Empresa Teste Ltda',
            nome_fantasia='Empresa Teste',
            cnpj='12345678000199',
            status='Ativa'
        )
        print(f'Empresa criada: {empresa.razao}')
    
    # Criar relacionamento usuário-empresa
    try:
        ue = UsuarioEmpresa.objects.get(usuario=user, empresa=empresa)
        print(f'Relacionamento já existe: {user.username} -> {empresa.razao}')
    except UsuarioEmpresa.DoesNotExist:
        ue = UsuarioEmpresa.objects.create(
            usuario=user,
            empresa=empresa,
            ativo=True
        )
        print(f'Relacionamento usuário-empresa criado: {user.username} -> {empresa.razao}')
    
    print('\\nConfiguração concluída com sucesso!')
    return user, empresa

if __name__ == "__main__":
    setup_initial_data()