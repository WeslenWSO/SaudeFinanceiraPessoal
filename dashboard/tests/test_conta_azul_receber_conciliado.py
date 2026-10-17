from decimal import Decimal

from django.test import SimpleTestCase

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
