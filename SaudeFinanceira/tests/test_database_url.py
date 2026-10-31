from django.test import SimpleTestCase

from SaudeFinanceira.database_url import host_postgres_da_url, normalizar_database_url


class DatabaseUrlNormalizeTest(SimpleTestCase):
    def test_host_sem_porta_ganha_5432(self):
        url = 'postgresql://u:p@dpg-abc-a/financas_db'
        out = normalizar_database_url(url)
        self.assertIn(':5432/', out)
        self.assertEqual(host_postgres_da_url(out), 'dpg-abc-a')

    def test_senha_colada_no_host(self):
        url = 'postgresql://financas_db_7enj_user:Secret123dpg-dbj3k7dg1s2s73eme4a0-a/financas_db_7enj'
        out = normalizar_database_url(url)
        self.assertIn('@dpg-dbj3k7dg1s2s73eme4a0-a', out)
        self.assertIn(':5432/', out)

    def test_url_ja_correta(self):
        url = 'postgresql://u:p@dpg-abc-a.oregon-postgres.render.com:5432/db'
        self.assertEqual(normalizar_database_url(url), url)
