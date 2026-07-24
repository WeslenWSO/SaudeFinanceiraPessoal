from dashboard.conta_azul_api import calcular_dre, get_transacoes, buscar_contas_a_receber
from datetime import datetime

# Testar a API
hoje = datetime.now()
data_inicio = hoje.replace(day=1).strftime('%Y-%m-%d')
data_fim = hoje.strftime('%Y-%m-%d')

print("Testando API Conta Azul...")
try:
    dre_data = calcular_dre(data_inicio, data_fim)
    print("DRE calculado com sucesso:")
    print(dre_data)
except Exception as e:
    print(f"Erro ao calcular DRE: {e}")

try:
    transacoes = get_transacoes(data_inicio, data_fim)
    print("Transações obtidas:")
    print(transacoes)
except Exception as e:
    print(f"Erro ao obter transações: {e}")

try:
    # Testar busca de contas a receber com filtros
    filtros = {
        'pagina': 1,
        'tamanho_pagina': 10,
        'data_vencimento_de': '2025-08-15',
        'data_vencimento_ate': '2025-08-20'
    }
    contas_receber = buscar_contas_a_receber(filtros)
    print("Contas a receber encontradas:")
    print(contas_receber)
except Exception as e:
    print(f"Erro ao buscar contas a receber: {e}")