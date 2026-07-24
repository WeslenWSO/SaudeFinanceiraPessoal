# nfse_rio_branco/services/riobranco_scraper.py
from __future__ import annotations
import time
import hashlib
from pathlib import Path
from typing import Iterable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options



class RioBrancoPortalScraper:
    def __init__(self, download_dir: Path, headless: bool = True, timeout: int = 60):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout


        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_prefs = {
             "download.default_directory": str(self.download_dir.resolve()),
             "download.prompt_for_download": False,
             "download.directory_upgrade": True,
             "safebrowsing.enabled": True,
        }
        chrome_options.add_experimental_option("prefs", chrome_prefs)
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, self.timeout)


    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass
# ---------- Fluxo principal ----------

    def login(self, usuario: str, senha: str):
        """Efetua login no portal. Se houver gov.br/captcha, o método aguarda confirmação manual."""
        d = self.driver
        # Tente o portal de login unificado da prefeitura (gov.br)
        d.get("https://contribuinte.riobranco.ac.gov.br/login/") # Pode redirecionar p/ gov.br


# Se a página exibir botão 'Entrar com gov.br', clique.
        try:
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'gov.br') or contains(., 'Entrar')]"))).click()
        except Exception:
            pass # Alguns ambientes já caem no formulário


# Tente localizar campos padrão de login
        def fill_if_exists(xpath, value):
            try:
                el = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                el.clear(); el.send_keys(value)
                return True
            except Exception:
                return False


        filled_user = fill_if_exists("//input[@type='text' or @name='username' or contains(@id,'cpf') or contains(@id,'usuario')]", usuario)
        filled_pass = fill_if_exists("//input[@type='password' or @name='password']", senha)


        if filled_user and filled_pass:
          # Tente enviar
          try:
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar') or @type='submit']"))).click()
          except Exception:
            pass


# Em portais com 2FA/captcha/gov.br, pare aqui e aguarde confirmação manual.
        self._wait_manual_auth_if_needed()


# Após login, navegar até Nota Fiscal Eletrônica
        self._go_to_nfse_home()

    def _wait_manual_auth_if_needed(self):
        time.sleep(15)


    def _go_to_nfse_home(self):
        d = self.driver
        # TODO: ajuste conforme menu real
        # Tente abrir atalho de NFS-e
        try:
           d.get("https://nota.riobranco.ac.gov.br/")
        except Exception:
           pass
# Aguarde algum elemento característico da home de NFS-e
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Nota Fiscal') or contains(., 'NFS-e')]")))


    def search_and_download_xmls(self, dt_ini: str, dt_fim: str) -> Iterable[Path]:
        """Pesquisa por período e baixa os XMLs das NFS-e emitidas. Retorna paths baixados."""
        d = self.driver
        # TODO: acessar página de consulta/listagem de NFS-e emitidas
        # Exemplos típicos: "Consulta", "Notas Emitidas", "Relatórios"
        try:
           self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Emitidas') or contains(., 'Consulta')]"))).click()
        except Exception:
           pass


# Preencher datas (placeholders genéricos)
        def set_date(xpath, value):
           try:
             el = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
             el.clear(); el.send_keys(value)
           except Exception:
             pass


        set_date("//input[contains(@name,'inicio') or contains(@id,'dataInicial') or @placeholder='Data inicial']", dt_ini)
        set_date("//input[contains(@name,'fim') or contains(@id,'dataFinal') or @placeholder='Data final']", dt_fim)


# Buscar
        try:
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Buscar') or contains(., 'Pesquisar')]"))).click()
        except Exception:
            pass


        time.sleep(3)


# Loop nas páginas/linhas e baixar XML uma a uma
        downloaded = []
        while True:
            rows = d.find_elements(By.XPATH, "//table//tr[td]")
            for r in rows:
               try:
# Botão/ícone de download XML na linha
                  btn = r.find_element(By.XPATH, ".//a[contains(., 'XML') or contains(@title,'XML') or contains(@href,'.xml')]")
               except Exception:
                  continue
               before = set(p.name for p in self.download_dir.glob("*") )
               btn.click()
               path = self._wait_new_file(before)
               if path:
                  downloaded.append(path)
# Verifica se existe próxima página
            try:
               next_btn = d.find_element(By.XPATH, "//a[contains(., 'Próxima') or contains(., '>>') or contains(@aria-label,'Próxima')]")
               if 'disabled' in next_btn.get_attribute('class'):
                   break
               next_btn.click(); time.sleep(2)
            except Exception:
                   break
        return downloaded


    def _wait_new_file(self, before_names: set[str]) -> Path | None:
         """Aguarda novo arquivo aparecer no diretório de download."""
         for _ in range(60):
           after = list(self.download_dir.glob("*"))
           for p in after:
               if p.name not in before_names and not p.name.endswith(".crdownload"):
                  return p
           time.sleep(1)
         return None


    @staticmethod
    def sha1_of_file(path: Path) -> str:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
               h.update(chunk)
        return h.hexdigest()