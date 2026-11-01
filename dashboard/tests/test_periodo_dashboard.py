from datetime import date

from django.test import SimpleTestCase

from dashboard.periodo_dashboard import (
    MAX_INTERVALO_DASHBOARD_DIAS,
    validar_intervalo_dashboard,
)


class PeriodoDashboardTest(SimpleTestCase):
    def test_intervalo_maximo_368_dias(self):
        ini = date(2026, 1, 1)
        fim_ok = date(2027, 1, 4)  # 368 dias entre as datas (limite)
        self.assertIsNone(validar_intervalo_dashboard(ini, fim_ok))
        fim_grande = date(2027, 1, 5)
        err = validar_intervalo_dashboard(ini, fim_grande)
        self.assertIn(str(MAX_INTERVALO_DASHBOARD_DIAS), err or '')

    def test_data_final_antes_da_inicial(self):
        err = validar_intervalo_dashboard(date(2026, 2, 10), date(2026, 2, 1))
        self.assertIsNotNone(err)
