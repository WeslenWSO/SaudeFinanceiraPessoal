#!/usr/bin/env python
import os
import sys
import django

# Configurar o Django ANTES de importar qualquer modelo
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

# Agora pode importar os modelos
from django.test import Client
from django.contrib.auth.models import User
from empresa.models import Empresa

def test_fechamento_repasse():
    print("=== TESTE DO FECHAMENTO DE REPASSE ===")
    
    # Criar cliente de teste
    client = Client()
    
    # Tentar acessar sem empresa na sessão
    print("\n1. Testando sem empresa na sessão:")
    response = client.get('/faturamento_medico/fechamento-repasse/')
    print(f"   Status code: {response.status_code}")
    print(f"   Redirect location: {response.get('Location', 'N/A')}")
    
    # Fazer login como admin
    print("\n2. Fazendo login:")
    login_success = client.login(username='admin', password='admin123')
    print(f"   Login successful: {login_success}")
    
    # Verificar empresa na sessão
    print("\n3. Verificando empresa na sessão:")
    session = client.session
    print(f"   Session keys: {list(session.keys())}")
    empresa_id = session.get('empresa_id')
    empresa_nome = session.get('empresa_nome')
    print(f"   Empresa ID: {empresa_id}")
    print(f"   Empresa nome: {empresa_nome}")
    
    # Tentar acessar com usuário logado
    print("\n4. Testando com usuário logado (sem empresa selecionada):")
    response = client.get('/faturamento_medico/fechamento-repasse/')
    print(f"   Status code: {response.status_code}")
    
    if response.status_code == 302:
        redirect_url = response.get('Location', 'N/A')
        print(f"   Redirect location: {redirect_url}")
        print("   ✅ REDIRECIONAMENTO CORRETO - Sistema está redirecionando para listagem")
    
    # Simular seleção de empresa
    print("\n5. Simulando seleção de empresa:")
    empresa = Empresa.objects.first()
    if empresa:
        session['empresa_id'] = empresa.id
        session['empresa_nome'] = empresa.razao
        session.save()
        print(f"   Empresa selecionada: {empresa.razao} (ID: {empresa.id})")
        
        # Testar novamente com empresa selecionada
        print("\n6. Testando com empresa selecionada:")
        response = client.get('/faturamento_medico/fechamento-repasse/')
        print(f"   Status code: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SUCESSO - Página carregou corretamente!")
            # Verificar se é uma página válida
            content = response.content.decode('utf-8')
            if 'fechamento' in content.lower() or 'repasse' in content.lower():
                print("   ✅ CONTEÚDO CORRETO - Página contém referência ao fechamento de repasse")
            else:
                print("   ⚠️  CONTEÚDO SUSPEITO - Página não contém referências esperadas")
        elif response.status_code == 302:
            print(f"   ⚠️  AINDA REDIRECIONANDO - Location: {response.get('Location')}")
    
    print("\n7. Testando lista de empresas:")
    response = client.get('/empresa/lista/')
    print(f"   Status code: {response.status_code}")
    
    print("\n=== TESTE CONCLUÍDO ===")

if __name__ == "__main__":
    test_fechamento_repasse()