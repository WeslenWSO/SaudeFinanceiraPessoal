from django.test import TestCase

from servicos_medicos.forms import ServicosMedicosForm
from servicos_medicos.models import ServicosMedicos


class ServicosMedicosFormTests(TestCase):
    def test_nao_permite_codigo_duplicado_no_cadastro(self):
        ServicosMedicos.objects.create(codigo='99999', servicos='Exame A')
        form = ServicosMedicosForm(data={
            'codigo': '99999',
            'servicos': 'Exame B',
            'porte_anestesico': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('codigo', form.errors)

    def test_permite_mesmo_codigo_na_edicao(self):
        obj = ServicosMedicos.objects.create(codigo='88888', servicos='Exame X')
        form = ServicosMedicosForm(
            data={'codigo': '88888', 'servicos': 'Exame X alterado', 'porte_anestesico': 1},
            instance=obj,
        )
        self.assertTrue(form.is_valid(), form.errors)
