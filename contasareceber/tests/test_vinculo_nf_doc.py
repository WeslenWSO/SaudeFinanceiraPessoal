from django.test import SimpleTestCase

from contasareceber.nf_sync_discriminacao import _digitos_nf, _variantes_numero_nf


class VinculoNumeroNfDocTests(SimpleTestCase):
    def test_variantes_zeros(self):
        v = _variantes_numero_nf('6666')
        self.assertIn('6666', v)
        self.assertIn('06666', v)

    def test_digitos_normaliza(self):
        self.assertEqual(_digitos_nf('06666'), '6666')
        self.assertEqual(_digitos_nf('NF-6690'), '6690')
