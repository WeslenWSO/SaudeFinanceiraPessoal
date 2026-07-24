#!/usr/bin/env python
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from faturamento_medico.models import FaturamentoMedico, ItemServico
from servicos_medicos.models import ServicosMedicos
from datetime import datetime
from django.utils import timezone

def test_import():
    # Ler o arquivo
    with open('UNIMED.txt', 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    # Pular cabeçalho
    data_lines = lines[1:]

    # Agrupar por lote e guia
    grupos = {}
    servicos_unicos = set()

    for line in data_lines:
        if not line.strip():
            continue
        parts = line.split(';')
        if len(parts) < 13:
            continue

        lote = parts[0].strip()
        guia = parts[1].strip()
        cod_usuario = parts[2].strip()
        nome_usuario = parts[3].strip()
        plano = parts[4].strip()
        cod_servico = parts[5].strip()
        desc_servico = parts[6].strip()
        tp_grau = parts[7].strip()
        data_str = parts[8].strip()
        qtde_via = parts[9].strip()
        valor_unit = parts[10].strip().replace(',', '.')
        valor_total = parts[11].strip().replace(',', '.')
        observacao = parts[12].strip() if len(parts) > 12 else ''

        # Converter data
        try:
            data = datetime.strptime(data_str, '%d/%m/%Y').date()
        except:
            data = timezone.now().date()

        chave = f"{lote}_{guia}"

        if chave not in grupos:
            grupos[chave] = {
                'lote': lote,
                'guia': guia,
                'carteirinha': cod_usuario,
                'nome': nome_usuario,
                'plano': plano,
                'data': data,
                'servicos': []
            }

        grupos[chave]['servicos'].append({
            'codigo': cod_servico,
            'descricao': desc_servico,
            'porte': tp_grau,
            'qt': int(float(qtde_via)) if qtde_via else 1,
            'valor': float(valor_unit) if valor_unit else 0,
            'total': float(valor_total) if valor_total else 0,
            'observacao': observacao
        })

        servicos_unicos.add((cod_servico, desc_servico))

    print(f"Encontrados {len(grupos)} grupos de faturamento")
    print(f"Encontrados {len(servicos_unicos)} serviços únicos")

    # Verificar serviços existentes
    servicos_existentes = ServicosMedicos.objects.filter(codigo__in=[s[0] for s in servicos_unicos]).values_list('codigo', flat=True)
    servicos_faltando = [s for s in servicos_unicos if s[0] not in servicos_existentes]

    print(f"Serviços já cadastrados: {len(servicos_existentes)}")
    print(f"Serviços a serem criados: {len(servicos_faltando)}")

    # Mostrar alguns exemplos
    print("\nExemplos de grupos:")
    for i, (chave, dados) in enumerate(list(grupos.items())[:3]):
        print(f"Grupo {i+1}: Lote {dados['lote']}, Guia {dados['guia']}, Nome {dados['nome']}, Serviços: {len(dados['servicos'])}")

    print("\nServiços faltando:")
    for cod, desc in servicos_faltando[:5]:
        print(f"{cod}: {desc}")

if __name__ == '__main__':
    test_import()