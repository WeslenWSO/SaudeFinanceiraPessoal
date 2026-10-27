from datetime import date

from django.test import SimpleTestCase

from dashboard.conta_azul.periodo_sync import (
    MAX_DIAS_SYNC_CONTA_AZUL,
    parse_periodo_sync,
    periodo_sync_padrao,
)


class PeriodoSyncTest(SimpleTestCase):
    def test_padrao_inicio_mes_ate_hoje(self):
        hoje = date(2026, 10, 27)
        de, ate = periodo_sync_padrao(hoje)
        self.assertEqual(de, date(2026, 10, 1))
        self.assertEqual(ate, hoje)

    def test_31_dias_ok(self):
        de, ate = parse_periodo_sync('2026-01-01', '2026-01-31')
        self.assertEqual((de, ate), (date(2026, 1, 1), date(2026, 1, 31)))

    def test_32_dias_rejeita(self):
        with self.assertRaises(ValueError) as ctx:
            parse_periodo_sync('2026-01-01', '2026-02-01')
        self.assertIn(str(MAX_DIAS_SYNC_CONTA_AZUL), str(ctx.exception))

    def test_fim_antes_inicio(self):
        with self.assertRaises(ValueError):
            parse_periodo_sync('2026-10-10', '2026-10-01')
