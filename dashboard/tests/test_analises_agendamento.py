from django.test import SimpleTestCase

from dashboard.analises_agendamento import (
    ROTULO_PENDENCIA_PACS,
    agendamento_conta_faturamento_convenio,
    agendamento_pendencia_pacs_convenio,
    eh_aguardando_faturamento_agendamento,
    eh_confirmado_pendencia_pacs,
    eh_concluido_agendamento,
    rotulo_exibicao_agendamento_dashboard,
)
from unittest.mock import MagicMock


class AnalisesAgendamentoTests(SimpleTestCase):
    def test_faturamento_aguardando_e_concluido(self):
        self.assertTrue(eh_aguardando_faturamento_agendamento('Aguardando faturamento'))
        self.assertTrue(eh_concluido_agendamento('Concluído'))
        self.assertFalse(eh_confirmado_pendencia_pacs('Concluído'))

    def test_pendencia_pacs_confirmado(self):
        self.assertTrue(eh_confirmado_pendencia_pacs('Confirmado'))
        self.assertTrue(eh_confirmado_pendencia_pacs('Confirmado online'))
        self.assertEqual(
            rotulo_exibicao_agendamento_dashboard('Confirmado'),
            ROTULO_PENDENCIA_PACS,
        )

    def test_conta_faturamento_faturamento_obj(self):
        aguard = MagicMock(status_agendamento='Aguardando faturamento')
        conf = MagicMock(status_agendamento='Confirmado')
        self.assertTrue(agendamento_conta_faturamento_convenio(aguard))
        self.assertFalse(agendamento_conta_faturamento_convenio(conf))
        self.assertTrue(agendamento_pendencia_pacs_convenio(conf))
