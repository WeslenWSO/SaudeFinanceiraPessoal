from unittest.mock import MagicMock

from django.test import SimpleTestCase

from faturamento_medico.services.acerto_caixa import (
    _eh_aguardando_faturamento,
    _item_conferencia_pendente,
)


class AcertoCaixaConferenciaHelpersTests(SimpleTestCase):
    def test_aguardando_faturamento_agendamento(self):
        self.assertTrue(_eh_aguardando_faturamento('Aguardando faturamento'))
        self.assertTrue(_eh_aguardando_faturamento('Aguardando o faturamento'))
        self.assertFalse(_eh_aguardando_faturamento('Concluído'))
        self.assertFalse(_eh_aguardando_faturamento('Confirmado'))

    def test_item_pendente_vs_conferido(self):
        pendente = MagicMock(
            status_conferencia='PENDENTE',
            conferido=False,
        )
        conferido = MagicMock(
            status_conferencia='CONFERIDO',
            conferido=True,
        )
        falta_guia = MagicMock(
            status_conferencia='FALTA DE GUIA',
            conferido=False,
        )
        self.assertTrue(_item_conferencia_pendente(pendente))
        self.assertFalse(_item_conferencia_pendente(conferido))
        self.assertFalse(_item_conferencia_pendente(falta_guia))
