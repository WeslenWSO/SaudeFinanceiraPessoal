from __future__ import annotations

import os
import re
import time
from datetime import date, datetime

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from empresa.models import Empresa
from empresa.nfse_nacional_config import nfse_nacional_resolvido_para_empresa
from notasfiscais.adn_nacional_client import distribuir_documentos_adn
from notasfiscais.nfse_xml_copia import salvar_baixados_portal_nacional_files, validar_periodo_xml_nfse
from notasfiscais.portal_nacional_client import baixar_nfse_pdf_por_chave
from notasfiscais.utils import import_nfse_from_xml
from notasfiscais.views import _extrair_chave_acesso_nfse_do_xml


class Command(BaseCommand):
    help = "Sincroniza ADN em loop (intervalo fixo) até data/hora limite."

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, required=True, help="ID da empresa.")
        parser.add_argument("--usuario", type=str, default="admin", help="Usuário para importação.")
        parser.add_argument("--inicio", type=str, required=True, help="Data inicial (YYYY-MM-DD).")
        parser.add_argument("--fim", type=str, required=True, help="Data final (YYYY-MM-DD).")
        parser.add_argument(
            "--ate",
            type=str,
            default="2026-04-23 12:00",
            help="Data/hora limite local (YYYY-MM-DD HH:MM).",
        )
        parser.add_argument(
            "--intervalo-min",
            type=int,
            default=45,
            help="Intervalo entre ciclos, em minutos.",
        )
        parser.add_argument(
            "--max-documentos",
            type=int,
            default=500,
            help="Máximo de documentos por ciclo de consulta ADN.",
        )

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(pk=options["empresa_id"]).first()
        if not empresa:
            raise CommandError("Empresa não encontrada.")

        user_model = get_user_model()
        user = user_model.objects.filter(username=options["usuario"]).first()
        if not user:
            raise CommandError("Usuário não encontrado.")

        try:
            di = date.fromisoformat(options["inicio"])
            df = date.fromisoformat(options["fim"])
            limite_local = datetime.strptime(options["ate"], "%Y-%m-%d %H:%M")
        except ValueError as e:
            raise CommandError(f"Data inválida: {e}")
        if di > df:
            raise CommandError("A data inicial não pode ser maior que a final.")

        limite = timezone.make_aware(limite_local, timezone.get_current_timezone())
        intervalo_seg = max(60, int(options["intervalo_min"]) * 60)

        self.stdout.write(
            self.style.SUCCESS(
                f"Iniciando loop ADN empresa={empresa.pk} intervalo={options['intervalo_min']}min ate={limite} periodo={di}..{df}"
            )
        )

        ciclos = 0
        while timezone.now() < limite:
            ciclos += 1
            self.stdout.write(f"\n[CICLO {ciclos}] {timezone.localtime(timezone.now())}")
            try:
                resumo = self._rodar_ciclo(empresa, user, di, df, int(options["max_documentos"]))
                self.stdout.write(self.style.SUCCESS(resumo))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Falha no ciclo: {e}"))

            if timezone.now() >= limite:
                break
            self.stdout.write(f"Aguardando {options['intervalo_min']} minutos...")
            time.sleep(intervalo_seg)

        self.stdout.write(self.style.SUCCESS("Loop finalizado."))

    def _rodar_ciclo(self, empresa, user, di: date, df: date, max_docs: int) -> str:
        cfg_nfse = nfse_nacional_resolvido_para_empresa(empresa)
        pfx_path = (cfg_nfse.get("pfx_path") or "").strip()
        pfx_password = cfg_nfse.get("pfx_password") or ""
        if not pfx_path or not os.path.isfile(pfx_path):
            raise CommandError("Certificado PFX não configurado/disponível para sincronização ADN.")

        cfg_adn = getattr(django_settings, "ADN_NFSE", {}) or {}
        adn_base_url = (cfg_adn.get("base_url") or "").strip()
        verify_ssl = bool(cfg_adn.get("verify_ssl", True))
        distribuicao_paths = cfg_adn.get("distribuicao_paths") or []
        fetch_rounds = max(1, int((cfg_adn.get("fetch_rounds") or 25)))
        period_scan_window_nsu = int((cfg_adn.get("period_scan_window_nsu") or 1200))

        doc_empresa = re.sub(r"\D", "", (empresa.cnpj or "").strip())
        if len(doc_empresa) not in (11, 14):
            raise CommandError("Empresa sem CNPJ/CPF válido para sincronização ADN.")

        nsu_base = int(empresa.nfse_adn_ultimo_nsu or 0)
        if period_scan_window_nsu > 0:
            nsu_base = max(0, nsu_base - period_scan_window_nsu)

        documentos = []
        payload = {}
        nsu_cur = nsu_base
        err = None
        for _ in range(fetch_rounds):
            payload, err = distribuir_documentos_adn(
                base_url=adn_base_url,
                pfx_path=pfx_path,
                pfx_password=pfx_password,
                cnpj=doc_empresa,
                ultimo_nsu=nsu_cur,
                verify_ssl=verify_ssl,
                distribuicao_paths=distribuicao_paths,
                max_documentos=max_docs,
            )
            if err:
                break
            docs = payload.get("documentos") or []
            documentos.extend(docs)
            nsu_next = int(payload.get("ultimo_nsu", nsu_cur) or nsu_cur)
            if nsu_next <= nsu_cur and not docs:
                break
            nsu_cur = nsu_next
            if len(documentos) >= max_docs:
                break

        if err and not documentos:
            raise CommandError(err)

        # dedup
        seen = set()
        dedup_docs = []
        for d in documentos:
            xb = d.get("xml_bytes") or b""
            key = f"{d.get('nsu')}|{d.get('chave')}|{repr(xb[:80])}"
            if key in seen:
                continue
            seen.add(key)
            dedup_docs.append(d)

        total_docs = len(dedup_docs)
        importadas = 0
        ignoradas = 0
        fora_periodo = 0
        erros = 0
        pdf_ok = 0
        pdf_fail = 0

        for idx, doc in enumerate(dedup_docs, start=1):
            xml_bytes = doc.get("xml_bytes")
            if not xml_bytes:
                erros += 1
                continue
            if validar_periodo_xml_nfse(xml_bytes, di, df):
                fora_periodo += 1
                continue
            chave = doc.get("chave") or _extrair_chave_acesso_nfse_do_xml(xml_bytes)
            pdf_bytes = None
            if chave:
                pdf_bytes, _ = baixar_nfse_pdf_por_chave(
                    chave,
                    pfx_path,
                    pfx_password,
                    cfg_nfse.get("base_url") or adn_base_url,
                    verify_ssl=verify_ssl,
                )
                if pdf_bytes:
                    pdf_ok += 1
                else:
                    pdf_fail += 1

            stem = f"nfse_adn_{doc.get('nsu') or idx}"
            salvar_baixados_portal_nacional_files(
                xml_bytes,
                pdf_bytes,
                stem,
                empresa,
                importar_canceladas=False,
            )
            uploaded = SimpleUploadedFile(f"{stem}.xml", xml_bytes, content_type="application/xml")
            try:
                resultado = import_nfse_from_xml(uploaded, user, empresa, importar_canceladas=False)
            except Exception:
                erros += 1
                continue
            importadas += int(resultado.get("total_importadas", 0))
            ignoradas += int(resultado.get("total_ignoradas", 0))

        nsu_final = int(payload.get("ultimo_nsu", empresa.nfse_adn_ultimo_nsu or 0) or 0)
        empresa.nfse_adn_ultimo_nsu = nsu_final
        empresa.nfse_adn_data_ultima_sincronizacao = timezone.now()
        empresa.save(update_fields=["nfse_adn_ultimo_nsu", "nfse_adn_data_ultima_sincronizacao"])

        return (
            f"ADN ciclo OK | docs={total_docs} importadas={importadas} ignoradas={ignoradas} "
            f"fora_periodo={fora_periodo} erros={erros} pdf_ok={pdf_ok} pdf_fail={pdf_fail} nsu={nsu_final}"
        )

