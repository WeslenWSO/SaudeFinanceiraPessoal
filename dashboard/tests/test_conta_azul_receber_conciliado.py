from decimal import Decimal

from django.test import SimpleTestCase

from datetime import date

from dashboard.conta_azul.periodo import parse_periodo_integracao_ca
from dashboard.conta_azul.receber_conciliado import (
    _baixas_conciliadas_parcela,
    _hash_lancamento_ca,
    _liquido_extrato_baixa,
    _marcador_baixa,
    _numero_nf_de_item,
)


class ReceberConciliadoContaAzulTest(SimpleTestCase):
    def test_marcador_baixa(self):
        self.assertIn('uuid-1', _marcador_baixa('uuid-1'))

    def test_hash_lancamento(self):
        self.assertTrue(_hash_lancamento_ca('rec-99').startswith('ca-reconc-'))

    def test_liquido_composicao(self):
        baixa = {
            'valor_composicao': {
                'valor_liquido': 250.5,
                'valor_bruto': 300,
            },
        }
        self.assertEqual(_liquido_extrato_baixa(baixa), Decimal('250.5'))

    def test_baixas_conciliadas_filtra_reconciliacao(self):
        det = {
            'baixas': [
                {'id': '1', 'id_reconciliacao': 'r1', 'tipo_evento_financeiro': 'RECEITA'},
                {'id': '2', 'tipo_evento_financeiro': 'RECEITA'},
            ],
        }
        self.assertEqual(len(_baixas_conciliadas_parcela(det)), 1)

    def test_numero_nf_fatura(self):
        item = {'fatura': {'numero': 4567, 'tipo_fatura': 'NFSE'}}
        self.assertEqual(_numero_nf_de_item(item), '4567')

    def test_periodo_dia(self):
        post = {'ca_periodo_modo': 'dia', 'ca_periodo_dia': '2026-03-15'}
        d1, d2, err = parse_periodo_integracao_ca(post)
        self.assertIsNone(err)
        self.assertEqual(d1, date(2026, 3, 15))
        self.assertEqual(d2, d1)

    def test_periodo_intervalo_31_dias_ok(self):
        post = {
            'ca_periodo_modo': 'intervalo',
            'ca_data_de': '2026-01-01',
            'ca_data_ate': '2026-01-31',
        }
        d1, d2, err = parse_periodo_integracao_ca(post)
        self.assertIsNone(err)
        self.assertEqual((d2 - d1).days, 30)

    def test_periodo_intervalo_rejeita_32_dias(self):
        post = {
            'ca_periodo_modo': 'intervalo',
            'ca_data_de': '2026-01-01',
            'ca_data_ate': '2026-02-01',
        }
        _, _, err = parse_periodo_integracao_ca(post)
        self.assertIsNotNone(err)
