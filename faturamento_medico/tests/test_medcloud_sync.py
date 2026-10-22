from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from faturamento_medico.medcloud.client import (
    STATUS_AGENDADOS_API,
    MedcloudRISClient,
)
from faturamento_medico.medcloud.sync import (
    _listar_agendas_ris,
    _status_agendamento_label,
)


class MedcloudStatusLabelTests(SimpleTestCase):
    def test_status_agendado_online(self):
        self.assertEqual(
            _status_agendamento_label({'status': 'ONLINE_SCHEDULED'}),
            'Agendado online',
        )


class MedcloudListarEscopoTests(SimpleTestCase):
    def test_escopo_agendados_chama_list_schedules_agendadas(self):
        ris = MagicMock(spec=MedcloudRISClient)
        ris.list_schedules_agendadas.return_value = [{'id': 1}]
        out = _listar_agendas_ris(
            ris, date(2026, 10, 1), date(2026, 10, 7), escopo='agendados', partner_id=None,
        )
        self.assertEqual(out, [{'id': 1}])
        ris.list_schedules_agendadas.assert_called_once()

    def test_status_agendados_api_inclui_confirmado(self):
        self.assertIn('CONFIRMED', STATUS_AGENDADOS_API)
