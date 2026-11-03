from decimal import Decimal

from django.test import TestCase

from empresa.models import Empresa
from servicos_medicos.models import Cabecalho, Convenio, ServicosMedicos, TabelaPreco
from servicos_medicos.replicar_tabela_preco import (
    contagem_faltantes_no_destino,
    replicar_tabela_preco,
)


class ReplicarTabelaPrecoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao="Teste LTDA", cnpj="00000000000100", nome_fantasia="Teste"
        )
        self.conv_a = Convenio.objects.create(empresa=self.empresa, nome="JARDEL")
        self.conv_b = Convenio.objects.create(empresa=self.empresa, nome="ADRIANA")
        self.cab_origem = Cabecalho.objects.create(
            empresa=self.empresa, convenio=self.conv_a, nome_tabela="TABELA - JARDEL"
        )
        self.cab_destino = Cabecalho.objects.create(
            empresa=self.empresa, convenio=self.conv_b, nome_tabela="TABELA - ADRIANA"
        )
        self.servico = ServicosMedicos.objects.create(codigo="40802012", servicos="RX TESTE")
        TabelaPreco.objects.create(
            empresa=self.empresa,
            convenio=self.conv_a,
            cabecalho=self.cab_origem,
            codigo_servico=self.servico,
            preco_apartamento=Decimal("90.00"),
            preco_enfermaria=Decimal("90.00"),
        )

    def test_somente_faltantes_nao_altera_existente(self):
        servico2 = ServicosMedicos.objects.create(codigo="40802013", servicos="US TESTE")
        TabelaPreco.objects.create(
            empresa=self.empresa,
            convenio=self.conv_a,
            cabecalho=self.cab_origem,
            codigo_servico=servico2,
            preco_apartamento=Decimal("50.00"),
            preco_enfermaria=Decimal("50.00"),
        )
        TabelaPreco.objects.create(
            empresa=self.empresa,
            convenio=self.conv_b,
            cabecalho=self.cab_destino,
            codigo_servico=self.servico,
            preco_apartamento=Decimal("1.00"),
            preco_enfermaria=Decimal("1.00"),
        )
        falt, ja = contagem_faltantes_no_destino(self.cab_origem, self.cab_destino)
        self.assertEqual(falt, 1)
        self.assertEqual(ja, 1)
        r = replicar_tabela_preco(
            self.cab_origem, self.cab_destino, atualizar_existentes=False
        )
        self.assertEqual(r.criados, 1)
        self.assertEqual(r.atualizados, 0)
        dest_rx = TabelaPreco.objects.get(
            cabecalho=self.cab_destino, codigo_servico=self.servico
        )
        self.assertEqual(dest_rx.preco_apartamento, Decimal("1.00"))
        self.assertTrue(
            TabelaPreco.objects.filter(
                cabecalho=self.cab_destino, codigo_servico=servico2
            ).exists()
        )

    def test_copia_para_destino(self):
        r = replicar_tabela_preco(self.cab_origem, self.cab_destino)
        self.assertEqual(r.total_origem, 1)
        self.assertEqual(r.criados, 1)
        self.assertTrue(
            TabelaPreco.objects.filter(
                cabecalho=self.cab_destino,
                codigo_servico=self.servico,
                preco_apartamento=Decimal("90.00"),
            ).exists()
        )

    def test_replica_somente_servicos_selecionados(self):
        servico2 = ServicosMedicos.objects.create(codigo="40802013", servicos="US TESTE")
        TabelaPreco.objects.create(
            empresa=self.empresa,
            convenio=self.conv_a,
            cabecalho=self.cab_origem,
            codigo_servico=servico2,
            preco_apartamento=Decimal("50.00"),
            preco_enfermaria=Decimal("60.00"),
        )
        r = replicar_tabela_preco(
            self.cab_origem,
            self.cab_destino,
            servico_ids=frozenset({servico2.pk}),
        )
        self.assertEqual(r.criados, 1)
        self.assertFalse(
            TabelaPreco.objects.filter(
                cabecalho=self.cab_destino, codigo_servico=self.servico
            ).exists()
        )
        dest = TabelaPreco.objects.get(
            cabecalho=self.cab_destino, codigo_servico=servico2
        )
        self.assertEqual(dest.preco_apartamento, Decimal("50.00"))
        self.assertEqual(dest.preco_enfermaria, Decimal("60.00"))

    def test_copia_quando_preco_esta_em_cabecalho_duplicado(self):
        cab_dup = Cabecalho.objects.create(
            empresa=self.empresa, convenio=self.conv_a, nome_tabela="TABELA - JARDEL"
        )
        TabelaPreco.objects.filter(cabecalho=self.cab_origem).update(cabecalho=cab_dup)
        r = replicar_tabela_preco(self.cab_origem, self.cab_destino)
        self.assertEqual(r.total_origem, 1)
        self.assertEqual(r.criados, 1)
