ue#!/usr/bin/env python
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from notasfiscais.models import NotaFiscalServico
from empresa.models import Empresa

def listar_receita_mensal():
    # Usar empresa específica conforme informado pelo usuário
    empresa = Empresa.objects.get(id=6)
    if not empresa:
        print("Nenhuma empresa encontrada")
        return

    print(f"Empresa: {empresa.razao}")
    print(f"CNPJ: {empresa.cnpj}")
    print()

    # Meses para verificar
    meses = [
        (2025, 1, "Janeiro 2025"),
        (2025, 2, "Fevereiro 2025"),
        (2025, 3, "Março 2025")
    ]

    for ano, mes, nome_mes in meses:
        # Calcular receita bruta do mês
        receita_mes = NotaFiscalServico.objects.filter(
            empresa_id=empresa.id,
            data_emissao__year=ano,
            data_emissao__month=mes
        ).aggregate(total=Sum('valor_bruto'))['total'] or 0

        # Contar notas fiscais
        count_notas = NotaFiscalServico.objects.filter(
            empresa_id=empresa.id,
            data_emissao__year=ano,
            data_emissao__month=mes
        ).count()

        print(f"{nome_mes}:")
        print(f"  Receita Bruta: R$ {receita_mes:.2f}")
        print(f"  Número de notas: {count_notas}")

        # Listar notas individuais se houver poucas
        if count_notas <= 10:
            notas = NotaFiscalServico.objects.filter(
                empresa_id=empresa.id,
                data_emissao__year=ano,
                data_emissao__month=mes
            ).order_by('numero_nota')

            for nota in notas:
                print(f"    NF {nota.numero_nota}: R$ {nota.valor_bruto:.2f} - {nota.data_emissao}")

        print()

if __name__ == '__main__':
    from django.db.models import Sum
    listar_receita_mensal()