# C:\Users\Administrador\Projetos\Python\saudefinanceira\nfse_rio_branco\management\commands\fetch_rio_branco_ws_nfse.py

import os
import hashlib
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import List

import certifi
import requests
from requests.exceptions import RequestException
from lxml import etree

# Set REQUESTS_CA_BUNDLE to certifi's CA bundle to avoid TLS errors
os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from nfse_rio_branco.models import Company, PortalCredential,\
    DownloadJob, Nfse
from nfse_rio_branco.services.abrasf_parser import parse_compnfse
from nfse_rio_branco.services.riobranco_ws import RioBrancoWS





class Command(BaseCommand):
    help = "Baixa NFS-e via WebService (Rio Branco) por período e salva no banco."

    def add_arguments(self, parser):
        parser.add_argument('--company', type=int, required=True, help='ID da Company')
        parser.add_argument('--inicio', type=str, required=True, help='Data inicial (DD/MM/AAAA)')
        parser.add_argument('--fim', type=str, required=True, help='Data final (DD/MM/AAAA)')
        parser.add_argument('--base', type=str, choices=['municipal', 'nacional'], default='municipal', help='Base de consulta (municipal ou nacional)')
        parser.add_argument('--base-url', type=str, help='Base URL do WS (opcional, sobrescreve o padrão da base selecionada)')
        parser.add_argument('--homologacao', action='store_true', help='Usar modo homologação')

    def handle(self, *args, **opts):
        company_id = opts['company']
        dt_ini_str = opts['inicio']
        dt_fim_str = opts['fim']
        base = opts['base']
        base_url = opts['base_url']
        homologacao = opts['homologacao']

        # Definir endpoint baseado na base
        if not base_url:
            if base == 'nacional':
                base_url = settings.NFSE_RIO_BRANCO_WS['endpoint_nacional']
            else:  # municipal
                base_url = settings.NFSE_RIO_BRANCO_WS['endpoint_municipal']

        # 1) Validar/normalizar datas
        try:
            dt_ini = datetime.strptime(dt_ini_str, "%d/%m/%Y").date()
            dt_fim = datetime.strptime(dt_fim_str, "%d/%m/%Y").date()
            if dt_ini > dt_fim:
                raise CommandError("Data inicial maior que a final.")
        except ValueError:
            raise CommandError("Formato de data inválido. Use DD/MM/AAAA.")

        # 2) Buscar empresa e credenciais WS
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            raise CommandError('Company não encontrada')

        try:
            cred = PortalCredential.objects.get(company=company)
        except PortalCredential.DoesNotExist:
            raise CommandError('Credenciais de WS não cadastradas para a Company')

        im = cred.im or company.inscricao_municipal
        if not im:
            raise CommandError("Inscrição Municipal não cadastrada")
        senha_ws = cred.senha_ws
        if not senha_ws:
            raise CommandError("Senha WS não cadastrada")

        # 3) Criar job
        job = DownloadJob.objects.create(
            company=company,
            inicio=dt_ini,
            fim=dt_fim,
            status=DownloadJob.Status.PENDENTE,
        )
        job.status = DownloadJob.Status.EM_ANDAMENTO
        job.append_log(f"Iniciando job WS ({base})...")
        job.save(update_fields=['status', 'log'])

        # 4) Diretório “só para padronizar” (mesmo WS não baixando via browser)
        downloads_dir = Path(settings.MEDIA_ROOT) / f"downloads/rio_branco_ws/{company.cnpj}"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        client = RioBrancoWS(
            endpoint=base_url,
            cnpj=company.cnpj,
            im=im,
            senha=senha_ws,
            homologacao=homologacao or cred.ws_homologa,
        )

        try:
            # 5) Buscar XMLs do período
            job.append_log(f"Consultando XMLs de {dt_ini_str} a {dt_fim_str}...")
            soap_response = client.consultar_nfse_prestador(dt_ini.strftime("%Y-%m-%d"), dt_fim.strftime("%Y-%m-%d"))
            xml_list = RioBrancoWS.extract_comp_nfse_list(soap_response)
            job.append_log(f"{len(xml_list)} XML(s) retornado(s) pelo WS.")

            # 7) Processar e persistir
            novos = 0
            ignorados = 0
            for idx, xml_str in enumerate(xml_list, start=1):
                try:
                    # normalização e hash (sha1 de XML canonizado)
                    xml_norm = etree.tostring(etree.fromstring(xml_str.encode('utf-8')), encoding='utf-8')
                    sha1 = hashlib.sha1(xml_norm).hexdigest()

                    if Nfse.objects.filter(sha1=sha1, company=company).exists():
                        ignorados += 1
                        job.append_log(f"[{idx}] Ignorado (duplicado) sha1={sha1[:10]}...")
                        continue

                    data = parse_compnfse(xml_str)

                    nfse = Nfse.objects.create(
                        company=company,
                        numero=data.get('numero') or f"WS-{idx}",
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
                    novos += 1
                    job.append_log(f"[{idx}] Salvo: NFS-e {nfse.numero}")
                except Exception as e_item:
                    job.append_log(f"[{idx}] Falha ao processar XML: {e_item}")

            job.append_log(f"Resumo: novos={novos}, duplicados={ignorados}")
            job.status = DownloadJob.Status.CONCLUIDO
            job.append_log("Concluído com sucesso (WS).")

        except Exception as e:
            job.status = DownloadJob.Status.ERRO
            job.append_log(f"Erro: {e}")
            if "500" in str(e):
                job.append_log("Erro 500: Verifique se as credenciais (CNPJ, IM, senha) estão corretas no portal de Rio Branco.")
            raise
        finally:
            job.save(update_fields=['status', 'log'])
