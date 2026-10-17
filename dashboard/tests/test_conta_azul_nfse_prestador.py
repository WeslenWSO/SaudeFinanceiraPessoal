from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from dashboard.conta_azul.nfse_prestador import (
    _campos_de_item_ca,
    _documento_cliente,
    _parse_data_item,
)


class ContaAzulNfsePrestadorTest(SimpleTestCase):
    def test_parse_data_competencia(self):
        item = {'data_competencia': '2024-03-15'}
        self.assertEqual(_parse_data_item(item), date(2024, 3, 15))

    def test_documento_cnpj(self):
        self.assertIn('/', _documento_cliente('12345678000190'))

    def test_campos_emitida(self):
        item = {
            'id': '550e8400-e29b-41d4-a716-446655440099',
            'numero_nfse': 42,
            'numero_rps': 100,
            'status': 'EMITIDA',
            'valor_total_nfse': 1500.5,
            'nome_cliente': 'CLIENTE TESTE',
            'documento_cliente': '12345678000190',
            'data_competencia': '2024-01-10',
            'numero_venda': '2001',
        }
        campos = _campos_de_item_ca(item, empresa=object())
        self.assertIsNotNone(campos)
        assert campos is not None
        self.assertEqual(campos['numero_nota'], '42')
        self.assertEqual(campos['valor_liquido'], Decimal('1500.5'))
        self.assertIsNone(campos['data_cancelamento'])

    def test_ignora_pendente(self):
        item = {'numero_nfse': 1, 'status': 'PENDENTE'}
        self.assertIsNone(_campos_de_item_ca(item, empresa=object()))
