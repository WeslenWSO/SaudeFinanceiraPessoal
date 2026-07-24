import os
import django
import sys

# Configurar Django
sys.path.append('c:/Users/Administrador/Projetos/Python/SaudeFinanceira')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from contasapagar.models import ContasaPagar
from empresa.models import Empresa

# Pegar a primeira empresa
empresa = Empresa.objects.first()
print(f"Empresa: {empresa}")

# Buscar contas pagas em setembro 2025
contas = ContasaPagar.objects.filter(
    fornecedor__empresa=empresa,
    dtPag__year=2025,
    dtPag__month=9,
    valorPago__gt=0
)

print(f"Encontradas {contas.count()} contas pagas em setembro 2025")

total = 0
for conta in contas:
    print(f"ID: {conta.id}, Valor Pago: {conta.valorPago}, Data Pag: {conta.dtPag}, Categoria: {conta.categoria}")
    total += float(conta.valorPago)

print(f"Total somado: {total}")

# Verificar se há contas com data futura
contas_futuras = ContasaPagar.objects.filter(
    fornecedor__empresa=empresa,
    dtPag__year=2025,
    dtPag__month=9,
    dtPag__day=1,
    valorPago__gt=0
)

print(f"Contas pagas exatamente em 01/09/2025: {contas_futuras.count()}")
for conta in contas_futuras:
    print(f"ID: {conta.id}, Valor Pago: {conta.valorPago}, Data Pag: {conta.dtPag}")