from django.test import SimpleTestCase

from servicos_medicos.import_planilha import (
    modelo_servicos_medicos_xlsx,
    modelo_tabela_preco_xlsx,
    parse_planilha_servicos,
    parse_planilha_tabela_preco,
)


class ImportPlanilhaServicosTests(SimpleTestCase):
    def test_modelo_e_parse_servicos(self):
        data = modelo_servicos_medicos_xlsx()
        linhas, avisos = parse_planilha_servicos(data)
        self.assertGreaterEqual(len(linhas), 1)
        self.assertEqual(linhas[0]['codigo'], '41001001')
        self.assertIn('RM', linhas[0]['servicos'])

    def test_parse_vazio_avisa(self):
        linhas, avisos = parse_planilha_servicos(b'not-excel')
        self.assertEqual(linhas, [])
        self.assertTrue(avisos)


class ImportPlanilhaTabelaTests(SimpleTestCase):
    def test_modelo_completo(self):
        data = modelo_tabela_preco_xlsx(cabecalho_fixo=False)
        linhas, avisos = parse_planilha_tabela_preco(data, cabecalho_fixo=False)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]['convenio'], 'PARTICULAR')

    def test_modelo_cabecalho_fixo(self):
        data = modelo_tabela_preco_xlsx(cabecalho_fixo=True)
        linhas, _ = parse_planilha_tabela_preco(data, cabecalho_fixo=True)
        self.assertEqual(len(linhas), 1)
        self.assertNotIn('convenio', linhas[0])
