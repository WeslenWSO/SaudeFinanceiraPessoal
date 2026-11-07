from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from contasareceber.car_nfse_listagem import CAR_NFSE_CA, CAR_NFSE_FK, status_car_nfse_listagem


class CarNfseListagemTests(SimpleTestCase):
    def test_vazio_sem_empresa(self):
        self.assertEqual(status_car_nfse_listagem(0, []), {})

    @patch('contasareceber.models.ContaAReceber')
    def test_marca_fk_e_ca(self, CarMock):
        nf1 = MagicMock(id=1, numero_nota='6376')
        nf2 = MagicMock(id=2, numero_nota='6375')
        qs_fk = MagicMock()
        qs_fk.values_list.return_value.distinct.return_value = [2]
        qs_ca = MagicMock()
        car = MagicMock(doc='6376', conta_azul_parcela_id='uuid-parcela', pk=99)
        qs_ca.__iter__ = lambda self: iter([car])
        qs_ca.only.return_value = qs_ca
        qs_ca.filter.return_value = qs_ca

        def filter_side_effect(**kwargs):
            if kwargs.get('nota_id__in'):
                return qs_fk
            return qs_ca

        CarMock.objects.filter.side_effect = filter_side_effect

        out = status_car_nfse_listagem(1, [nf1, nf2])
        self.assertEqual(out[2], CAR_NFSE_FK)
        self.assertEqual(out[1], CAR_NFSE_CA)
