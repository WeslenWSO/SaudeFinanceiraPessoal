from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from faturamento_medico.services.vincular_nota_solicitante import (
    _nome_paciente_nota,
    _rotulo_tomador_paciente_nota,
)


class VincularNotaNomeExibicaoTest(SimpleTestCase):
    def test_discriminacao_incoerente_usa_tomador(self):
        disc = (
            '2 US DOPPLER 700,00\n'
            'EXAME REALIZADO PELO PACIENTE:JEFERSON GOMES DE SANTANA\n'
            'PARCERIA: X'
        )
        nota = MagicMock(
            pk=1,
            cliente='ADRIANE BRITO DO NASCIMENTO',
            discriminacao=disc,
            valor_liquido=Decimal('150'),
            valor_bruto=Decimal('150'),
        )
        self.assertEqual(_nome_paciente_nota(nota), 'ADRIANE BRITO DO NASCIMENTO')
        self.assertEqual(_rotulo_tomador_paciente_nota(nota), 'ADRIANE BRITO DO NASCIMENTO')
