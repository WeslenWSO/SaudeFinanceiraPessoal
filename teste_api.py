# Teste manual — informe CONTA_AZUL_* no .env e empresa_id
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from empresa.models import Empresa

empresa = Empresa.objects.first()
if not empresa:
    print('Nenhuma empresa no banco.')
else:
    from dashboard.conta_azul_api import calcular_dre
    print(f'Testando empresa {empresa.pk}...')
    try:
        print(calcular_dre(empresa.pk, '2025-01-01', '2025-01-31'))
    except Exception as e:
        print(f'Erro: {e}')
