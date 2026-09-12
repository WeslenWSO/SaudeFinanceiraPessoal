"""Cadastra convênios por nome de viabilidade e aplica alíquotas padrão."""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from decimal import Decimal

from empresa.models import Empresa
from servicos_medicos.models import Convenio

ALIQUOTAS = {
    'aliquota_iss_ap': Decimal('3'),
    'aliquota_pis_ap': Decimal('0.65'),
    'aliquota_cofins_ap': Decimal('3'),
    'aliquota_csll_ap': Decimal('2.88'),
    'aliquota_irpj_ap': Decimal('4.8'),
}

NOMES = [
    'ADRIANA MARINHO',
    'CARTÃO SANTA JULIANA',
    'DESPACHANTE AB',
    'NOSSA CLÍNICA DESPACHANTE MÉDICO',
    'OAB',
    'REAL CONVÊNIOS',
    'SESI SAUDE',
]

empresa_id = int(sys.argv[1]) if len(sys.argv) > 1 else 16
empresa = Empresa.objects.filter(pk=empresa_id).first()
if not empresa:
    raise SystemExit(f'Empresa {empresa_id} não encontrada')

for nome in NOMES:
    obj, created = Convenio.objects.update_or_create(
        empresa=empresa,
        nome=nome,
        defaults=ALIQUOTAS,
    )
    if not created:
        for k, v in ALIQUOTAS.items():
            setattr(obj, k, v)
        obj.save(update_fields=list(ALIQUOTAS.keys()))
    print(('CRIADO' if created else 'OK   '), nome)

print(f'Total convênios empresa {empresa_id}:', Convenio.objects.filter(empresa_id=empresa_id).count())
