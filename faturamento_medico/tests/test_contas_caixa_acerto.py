from unittest.mock import MagicMock

from django.test import SimpleTestCase

from faturamento_medico.services.contas_caixa_acerto import (
    conta_ativa_no_acerto_caixa,
    conta_elegivel_acerto_caixa,
)


class ContasCaixaAcertoTest(SimpleTestCase):
    def test_outros_sem_caixa_na_descricao_nao_elegivel(self):
        conta = MagicMock(tipo='OUTROS', descricao='Adiantamento de Fornecedor')
        self.assertFalse(conta_elegivel_acerto_caixa(conta))

    def test_tipo_caixa_elegivel(self):
        conta = MagicMock(tipo='CAIXA', descricao='CAIXA - BEATRIZ')
        self.assertTrue(conta_elegivel_acerto_caixa(conta))

    def test_inativo_acerto_nao_ativo(self):
        conta = MagicMock(
            tipo='CAIXA',
            descricao='CAIXA - BEATRIZ',
            inativo_acerto_caixa=True,
            status='A',
        )
        self.assertFalse(conta_ativa_no_acerto_caixa(conta))

    def test_encerrada_nao_ativa(self):
        conta = MagicMock(
            tipo='CAIXA',
            descricao='CAIXA - HELEN - ENCERRADA',
            inativo_acerto_caixa=False,
            status='A',
        )
        self.assertFalse(conta_ativa_no_acerto_caixa(conta))

    def test_ativa_no_acerto(self):
        conta = MagicMock(
            tipo='CAIXA',
            descricao='CAIXA - LAURA SILVA',
            inativo_acerto_caixa=False,
            status='A',
        )
        self.assertTrue(conta_ativa_no_acerto_caixa(conta))