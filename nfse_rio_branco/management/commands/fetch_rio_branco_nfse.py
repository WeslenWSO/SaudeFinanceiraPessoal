# nfse_rio_branco/management/commands/fetch_rio_branco_nfse.py
from __future__ import annotations
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from pathlib import Path
import hashlib
#from nfse_rio_branco.models import Company, PortalCredential, Nfse, DownloadJob
#from nfse_rio_branco.services.riobranco_scraper import RioBrancoPortalScraper
#from nfse_rio_branco.services.abrasf_parser import parse_compnfse
from lxml import etree
from decimal import Decimal




from nfse_rio_branco.services.riobranco_scraper import RioBrancoPortalScraper
from nfse_rio_branco.services.abrasf_parser import parse_compnfse
# ...existing code...
from nfse_rio_branco.models import DownloadJob, Company, PortalCredential, Nfse
# ...existing code...


class Command(BaseCommand):
  help = "Baixa NFS-e no portal de Rio Branco por período e salva no banco."
  
  def add_arguments(self, parser):
    parser.add_argument('--company', type=int, required=True, help='ID da Company')
    parser.add_argument('--inicio', type=str, required=True, help='Data inicial (DD/MM/AAAA)')
    parser.add_argument('--fim', type=str, required=True, help='Data final (DD/MM/AAAA)')
    parser.add_argument('--headless', action='store_true')


  def handle(self, *args, **opts):
     company_id = opts['company']
     dt_ini = opts['inicio']
     dt_fim = opts['fim']
     headless = opts['headless']


     try:
       company = Company.objects.get(pk=id)
       cred = PortalCredential.objects.get(company=company)
     except Company.DoesNotExist:
       raise CommandError('Company não encontrada')
     except PortalCredential.DoesNotExist:
      raise CommandError('Credenciais não cadastradas para a Company')


     job = DownloadJob.objects.create(company=company, inicio=dt_ini.split('/')[::-1], fim=dt_fim.split('/')[::-1])
     job.status = DownloadJob.Status.EM_ANDAMENTO; job.save(update_fields=['status'])


     downloads_dir = Path(settings.MEDIA_ROOT) / f"downloads/rio_branco/{company.cnpj}"
     scraper = RioBrancoPortalScraper(download_dir=downloads_dir, headless=headless)


     try:
      job.append_log("Iniciando login...")
      scraper.login(cred.usuario, cred.senha)


      job.append_log(f"Buscando notas de {dt_ini} a {dt_fim}...")
      files = scraper.search_and_download_xmls(dt_ini, dt_fim)
      job.append_log(f"{len(files)} arquivo(s) baixado(s)")


      for path in files:
          xml_str = path.read_text(encoding='utf-8', errors='ignore')
          # Normaliza e calcula hash
          xml_norm = etree.tostring(etree.fromstring(xml_str.encode('utf-8')), encoding='utf-8')
          sha1 = hashlib.sha1(xml_norm).hexdigest()
          if Nfse.objects.filter(sha1=sha1, company=company).exists():
             job.append_log(f"Ignorado (duplicado): {path.name}")
             continue


          data = parse_compnfse(xml_str)
          nfse = Nfse.objects.create(
            company=company,
            numero=data.get('numero') or path.stem,
            serie=data.get('serie'),
            codigo_verificacao=data.get('codigo_verificacao'),
            data_emissao=data.get('data_emissao'),
            competencia=data.get('competencia'),
            valor_servico=Decimal(str(data.get('valor_servico') or '0')),
            iss_retido=bool(data.get('iss_retido')),
            prestador_cnpj=data.get('prestador_cnpj'),
            tomador_cnpj_cpf=data.get('tomador_cnpj_cpf'),
            xml=xml_str,
            sha1=sha1,
          )
          job.append_log(f"Salvo: NFS-e {nfse.numero}")


      job.status = DownloadJob.Status.CONCLUIDO
      job.append_log("Concluído com sucesso.")


     except Exception as e:
      job.status = DownloadJob.Status.ERRO
      job.append_log(f"Erro: {e}")
      raise
     finally:
      job.save(update_fields=['status', 'log'])
      scraper.close()