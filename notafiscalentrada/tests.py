from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empresa.models import Empresa
from notafiscalentrada.models import NotaFiscalEntrada, NotaFiscalEntradaItem, ProdutoComercioFoto
from notafiscalentrada.produto_foto import mapa_fotos_por_codigo, url_google_imagens


class ProdutosComercioListTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Emp Teste', cnpj='12345678000199')
        self.user = User.objects.create_user('nf_user', password='x')
        self.client = Client()
        self.client.login(username='nf_user', password='x')
        session = self.client.session
        session['empresa_id'] = self.empresa.pk
        session.save()

        dt = timezone.make_aware(datetime(2026, 3, 15, 10, 0, 0))
        self.nota = NotaFiscalEntrada.objects.create(
            empresa=self.empresa,
            tipo_nota='comercio',
            chave_acesso='1' * 44,
            numero_nota='100',
            serie='1',
            fornecedor_cnpj='12345678000100',
            fornecedor_nome='Fornecedor A',
            destinatario_cnpj='12345678000199',
            destinatario_nome='Emp Teste',
            data_emissao=dt,
            valor_total=Decimal('100.00'),
        )
        NotaFiscalEntradaItem.objects.create(
            nota_fiscal=self.nota,
            numero_item=1,
            codigo_produto='P001',
            nome_produto='Sofa Especial',
            cfop='5102',
            unidade='UN',
            quantidade=Decimal('2'),
            valor_unitario=Decimal('50'),
            valor_total=Decimal('100'),
        )

    def test_lista_produto_por_periodo(self):
        url = reverse('notafiscalentrada:produtos_comercio')
        r = self.client.get(url, {'data_inicio': '2026-03-01', 'data_fim': '2026-03-31', 'produto': 'Sofa'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Sofa Especial')
        self.assertContains(r, 'P001')

    def test_filtro_fornecedor(self):
        url = reverse('notafiscalentrada:produtos_comercio')
        r = self.client.get(
            url,
            {
                'data_inicio': '2026-03-01',
                'data_fim': '2026-03-31',
                'fornecedor': 'Fornecedor A',
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Sofa Especial')
        r2 = self.client.get(
            url,
            {
                'data_inicio': '2026-03-01',
                'data_fim': '2026-03-31',
                'fornecedor': 'Inexistente',
            },
        )
        self.assertNotContains(r2, 'Sofa Especial')

    def test_coluna_foto_usa_proxy_de_imagem(self):
        url = reverse('notafiscalentrada:produtos_comercio')
        r = self.client.get(url, {'data_inicio': '2026-03-01', 'data_fim': '2026-03-31'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse('notafiscalentrada:produto_comercio_foto_img'))
        self.assertContains(r, 'produto-foto-img')
        self.assertContains(r, 'P001')

    def test_mapa_fotos_cache(self):
        ProdutoComercioFoto.objects.create(
            empresa=self.empresa,
            codigo_produto='P001',
            url_imagem='https://example.com/foto.jpg',
        )
        m = mapa_fotos_por_codigo(self.empresa.pk, ['P001', 'X'])
        self.assertEqual(m['P001'], 'https://example.com/foto.jpg')
