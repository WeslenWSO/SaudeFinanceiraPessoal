#!/usr/bin/env python
"""
Script para testar a função processar_baixa_com_ajustes com logs de debug
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
sys.path.append('.')
django.setup()

from contasareceber.models import ContaAReceber, BaixaContaAReceber
from contasareceber.forms import BaixaContaIndividualForm
from empresa.models import Empresa
from django.contrib.auth.models import User
from django.test import RequestFactory
from datetime import date

def test_baixa_direta():
    """Testa a baixa direta com logs de debug"""
    print("=== TESTE DE BAIXA DIRETA ===")

    try:
        # Obter empresa (assumindo que existe)
        empresa = Empresa.objects.first()
        if not empresa:
            print("ERRO: Nenhuma empresa encontrada")
            return

        print(f"Empresa: {empresa}")

        # Obter uma conta a receber pendente
        conta = ContaAReceber.objects.filter(empresa=empresa, status='pendente').first()
        if not conta:
            print("ERRO: Nenhuma conta a receber pendente encontrada")
            return

        print(f"Conta: {conta}")
        print(f"Valor pendente: R$ {conta.get_valor_pendente()}")

        # Criar usuário (ou obter existente)
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')

        # Criar request factory
        factory = RequestFactory()

        # Simular dados do formulário
        form_data = {
            'data_recebimento': date.today().isoformat(),
            'valor_recebido': str(conta.get_valor_pendente()),
            'desconto': '0',
            'juros': '0',
            'tarifas': '0',
            'tipo_baixa': 'total',
            'observacao': 'Teste de baixa direta',
        }

        # Criar formulário
        form = BaixaContaIndividualForm(data=form_data, empresa_id=empresa.id, conta=conta)

        print(f"Formulário válido: {form.is_valid()}")
        if not form.is_valid():
            print(f"Erros do formulário: {form.errors}")
            return

        # Criar request
        request = factory.post('/contasareceber/baixar/', form_data)
        request.user = user
        request.session = {'empresa_id': empresa.id}

        # Importar e chamar a função
        from contasareceber.views import processar_baixa_com_ajustes

        print("\n=== CHAMANDO processar_baixa_com_ajustes ===")
        result = processar_baixa_com_ajustes(conta, form, [], user, request)

        print(f"\nResultado: {result}")
        print("=== TESTE CONCLUÍDO ===")

    except Exception as e:
        print(f"ERRO GERAL: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_baixa_direta()