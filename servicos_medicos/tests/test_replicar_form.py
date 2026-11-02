from django.test import SimpleTestCase

from servicos_medicos.forms import ReplicarTabelaPrecoForm


class ReplicarFormChoicesTests(SimpleTestCase):
    def test_campos_sao_typed_choice_com_coerce_int(self):
        form = ReplicarTabelaPrecoForm()
        field = form.fields["cabecalho_origem"]
        self.assertEqual(field.coerce, int)
