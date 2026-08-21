from django.test import SimpleTestCase

from faturamento_medico.convenio_nf_utils import convenio_mostra_nf_pagamento


class ConvenioNfPagamentoTest(SimpleTestCase):
    def test_bradesco_saude_nao_exibe_nf(self):
        self.assertFalse(convenio_mostra_nf_pagamento('BRADESCO SAUDE S.A.'))
        self.assertFalse(convenio_mostra_nf_pagamento('Bradesco'))

    def test_convenio_particular_exibe_nf(self):
        self.assertTrue(convenio_mostra_nf_pagamento('UNIMED'))
        self.assertTrue(convenio_mostra_nf_pagamento(''))

    def test_fusex_variantes_nao_exibem_nf(self):
        self.assertFalse(convenio_mostra_nf_pagamento('FUSEX ISENTO'))
        self.assertFalse(convenio_mostra_nf_pagamento('FUSEX PASS'))
