#!/usr/bin/env python
"""
Script para adicionar a coluna conta_contabil à tabela ContaBancaria
Execute este script quando conseguir resolver o problema de dependências do Django
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from django.db import connection

def add_conta_contabil_column():
    """Adiciona a coluna conta_contabil à tabela extrato_contabancaria"""
    with connection.cursor() as cursor:
        try:
            # Verificar se a coluna já existe
            cursor.execute("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'extrato_contabancaria'
                AND COLUMN_NAME = 'conta_contabil'
            """)

            if cursor.fetchone():
                print("A coluna conta_contabil já existe na tabela.")
                return

            # Adicionar a coluna
            cursor.execute("""
                ALTER TABLE extrato_contabancaria
                ADD COLUMN conta_contabil VARCHAR(20) NULL
            """)

            print("Coluna conta_contabil adicionada com sucesso!")

        except Exception as e:
            print(f"Erro ao adicionar coluna: {e}")

if __name__ == '__main__':
    add_conta_contabil_column()