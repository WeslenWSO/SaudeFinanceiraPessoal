#!/usr/bin/env python
"""
Script de teste para verificar a serialização JSON
"""

import os
import sys
import django
import json
from decimal import Decimal

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

def test_serialization():
    """Testa a serialização de dados com valores Decimal"""
    
    print("=== TESTE DE SERIALIZAÇÃO JSON ===")
    
    # Simular o resultado da importação
    resultado_teste = {
        'nfses': [],  # Lista vazia de objetos Django
        'notas_importadas': [
            {
                'numero_nota': '1-406',
                'cliente': 'Cliente Teste',
                'valor_liquido': Decimal('1000.50')  # Valor Decimal
            },
            {
                'numero_nota': '1-407',
                'cliente': 'Cliente Teste 2',
                'valor_liquido': Decimal('2000.75')  # Valor Decimal
            }
        ],
        'notas_ignoradas': [
            {
                'numero_nota': '1-408',
                'cliente': 'Cliente Existente',
                'motivo': 'Nota já existe no banco'
            }
        ],
        'total_processadas': 3,
        'total_importadas': 2,
        'total_ignoradas': 1
    }
    
    print("Resultado original:")
    print(f"  - Total processadas: {resultado_teste['total_processadas']}")
    print(f"  - Total importadas: {resultado_teste['total_importadas']}")
    print(f"  - Total ignoradas: {resultado_teste['total_ignoradas']}")
    print(f"  - Primeira nota valor: {resultado_teste['notas_importadas'][0]['valor_liquido']} (tipo: {type(resultado_teste['notas_importadas'][0]['valor_liquido'])})")
    
    # Testar serialização manual
    def convert_decimal(obj):
        """Converte valores Decimal para float recursivamente"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {key: convert_decimal(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimal(item) for item in obj]
        else:
            return obj
    
    resultado_serializado = convert_decimal(resultado_teste)
    
    print("\nResultado serializado:")
    print(f"  - Primeira nota valor: {resultado_serializado['notas_importadas'][0]['valor_liquido']} (tipo: {type(resultado_serializado['notas_importadas'][0]['valor_liquido'])})")
    
    # Testar serialização JSON
    try:
        json_str = json.dumps(resultado_serializado, indent=2)
        print("\n✅ Serialização JSON bem-sucedida!")
        print("JSON gerado:")
        print(json_str[:200] + "..." if len(json_str) > 200 else json_str)
        
        # Testar desserialização
        resultado_deserializado = json.loads(json_str)
        print("\n✅ Desserialização JSON bem-sucedida!")
        print(f"  - Primeira nota valor: {resultado_deserializado['notas_importadas'][0]['valor_liquido']} (tipo: {type(resultado_deserializado['notas_importadas'][0]['valor_liquido'])})")
        
    except Exception as e:
        print(f"\n❌ Erro na serialização JSON: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_serialization()



