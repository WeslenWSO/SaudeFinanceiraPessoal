"""
Cliente para consultar NFSe no ambiente nacional (SEFIN) com mTLS (PFX).

Fluxo principal na aplicação: GET por identificador da DPS (42 dígitos).
Funções por chave de acesso permanecem disponíveis para integrações pontuais.

Documentação oficial (rotas diferem entre homologação e produção):
- Homologação: https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional/docs/index#tag/DPS
- Produção: https://sefin.nfse.gov.br/SefinNacional/docs/index
- Swagger produção: https://sefin.nfse.gov.br/SefinNacional/swagger/docs/v1
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import tempfile
import time
from typing import Optional, Tuple

import requests
from cryptography.hazmat.backends import default_backend
from django.conf import settings
from empresa.nfse_nacional_url import normalizar_base_url_sefin
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

logger = logging.getLogger(__name__)


def _sefin_request_timeout() -> Tuple[float, float]:
    """(connect, read) em segundos — evita um único valor alto só para «read» e «connect» iguais."""
    cfg = getattr(settings, "NFSE_NACIONAL", {}) or {}
    try:
        c = float(cfg.get("connect_timeout", 120))
    except (TypeError, ValueError):
        c = 120.0
    try:
        r = float(cfg.get("read_timeout", 180))
    except (TypeError, ValueError):
        r = 180.0
    return (max(5.0, c), max(10.0, r))


def _sefin_max_retries() -> int:
    cfg = getattr(settings, "NFSE_NACIONAL", {}) or {}
    try:
        return max(0, int(cfg.get("max_retries", 2)))
    except (TypeError, ValueError):
        return 2


def _requests_get_mtls(
    url: str,
    cert_pem_path: str,
    key_pem_path: str,
    *,
    verify_ssl: bool,
    headers: dict[str, str],
) -> requests.Response:
    """
    GET com mTLS; repetir em timeout/conexão (rede ou SEFIN instável).
    """
    timeout = _sefin_request_timeout()
    retries = _sefin_max_retries()
    last_exc: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            return requests.get(
                url,
                cert=(cert_pem_path, key_pem_path),
                timeout=timeout,
                verify=verify_ssl,
                headers=headers,
            )
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
        ) as e:
            last_exc = e
            if attempt < retries:
                delay = 2.0 * (attempt + 1)
                logger.warning(
                    "SEFIN GET falha de rede (tentativa %s/%s), aguardar %ss e repetir: %s — %s",
                    attempt + 1,
                    retries + 1,
                    delay,
                    url,
                    e,
                )
                time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("SEFIN GET: falha sem exceção registrada")


def _base_sefin_ou_erro(base_url: str) -> Tuple[str, Optional[str]]:
    """
    Retorna (base normalizada, None) ou ('', mensagem) se não for uma URL http(s) usável.
    """
    base = normalizar_base_url_sefin(base_url or "")
    if not base:
        return "", "URL base da SEFIN vazia. Configure na empresa ou NFSE_NACIONAL_BASE_URL."
    if not base.lower().startswith(("http://", "https://")):
        return (
            "",
            "URL base da SEFIN inválida. Informe apenas a URL (ex.: https://sefin.nfse.gov.br), sem texto antes de https://.",
        )
    return base, None


def _prefixos_rota_sefin_nacional(base_url: str) -> list[str]:
    """
    Ordem dos prefixos de path conforme o host.

    Em **produção restrita** a documentação expõe ``/API/SefinNacional/``.
    Em **produção** (``sefin.nfse.gov.br``) a API fica sob ``/SefinNacional/``;
    ``/API/SefinNacional/`` nesse host devolve **404** (IIS) — não incluir na lista.
    """
    b = normalizar_base_url_sefin(base_url).lower()
    if "producaorestrita" in b:
        return ["/API/SefinNacional", "/SefinNacional", "/sefinnacional"]
    return ["/SefinNacional", "/sefinnacional"]


def _headers_get_sefin() -> dict[str, str]:
    """API v1 troca JSON em vários endpoints; DPS pode devolver JSON com chave ou XML."""
    return {
        "Accept": "application/xml, application/json;q=0.9, */*;q=0.1",
        "Accept-Charset": "utf-8",
    }


def _extrair_chave_nfse_json(body: bytes) -> Optional[str]:
    """Se a consulta DPS retornar JSON com a chave de acesso, extrai só os dígitos."""
    try:
        text = body.decode("utf-8").strip()
        if not text.startswith("{"):
            return None
        data = json.loads(text)
    except Exception:
        return None

    def walk(obj: object) -> Optional[str]:
        if isinstance(obj, str):
            s = re.sub(r"\D", "", obj)
            if len(s) >= 40:
                return s
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                if "chave" in lk and isinstance(v, str):
                    s = re.sub(r"\D", "", v)
                    if len(s) >= 40:
                        return s
                r = walk(v)
                if r:
                    return r
        if isinstance(obj, list):
            for it in obj:
                r = walk(it)
                if r:
                    return r
        return None

    return walk(data)


def _detalhe_erro_json_resposta_sefin(body: bytes) -> Optional[str]:
    """
    Corpo JSON de erro da API SEFIN (ex.: HTTP 404 com E2404).
    O campo ``tipoAmbiente`` aqui segue a convenção da **API**, não o ``tpAmb``
    do XML da DPS/NFSe (no layout nacional costuma ser 1=produção, 2=homologação).
    """
    try:
        text = body.decode("utf-8").strip()
        if not text.startswith("{"):
            return None
        d = json.loads(text)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    err = d.get("erro")
    if not isinstance(err, dict):
        return None
    cod = err.get("codigo") or err.get("Codigo")
    desc = (err.get("descricao") or err.get("Descricao") or "").strip()
    if not cod and not desc:
        return None
    partes = []
    if cod:
        partes.append(str(cod))
    if desc:
        partes.append(desc)
    msg = " — ".join(partes)
    ta = d.get("tipoAmbiente")
    if ta is not None:
        msg += (
            f" [tipoAmbiente={ta} na resposta JSON da API; "
            f"não confundir com <tpAmb> do XML, onde 1=produção e 2=homologação.]"
        )
    return msg


def normalizar_chave_acesso(chave: str) -> str:
    return re.sub(r"\s+", "", (chave or "").strip())


def _pfx_para_pem_temporarios(
    pfx_path: str, pfx_password: str
) -> Tuple[str, str]:
    """Retorna (caminho_cert_pem, caminho_key_pem) temporários; o chamador deve apagar após uso."""
    with open(pfx_path, "rb") as f:
        blob = f.read()
    pwd = pfx_password.encode("utf-8") if pfx_password else None
    key, cert, _chain = pkcs12.load_key_and_certificates(blob, pwd, default_backend())
    if cert is None or key is None:
        raise ValueError("PFX sem certificado ou chave privada.")

    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())

    cf = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    kf = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    try:
        cf.write(cert_pem)
        kf.write(key_pem)
        cf.flush()
        kf.flush()
        return cf.name, kf.name
    finally:
        cf.close()
        kf.close()


def _parece_xml_xml(content: bytes) -> bool:
    if not content or len(content) < 20:
        return False
    head = content.lstrip()[:500]
    try:
        t = head.decode("utf-8", errors="ignore").lower()
    except Exception:
        return False
    return "<?xml" in t or "<nfse" in t or "infnfse" in t or "sped.fazenda.gov.br" in t


def _baixar_xml_urls_mtls(
    urls: list[str],
    pfx_path: str,
    pfx_password: str,
    *,
    verify_ssl: bool = True,
    json_chave_fallback_base: str = "",
) -> Tuple[Optional[bytes], Optional[str]]:
    """GET com mTLS em lista de URLs até obter XML de NFSe.

    Se ``json_chave_fallback_base`` estiver preenchido e a resposta 200 for JSON
    com chave de acesso (consulta DPS na API nacional), tenta GET do XML pela chave.
    """
    if not pfx_path or not os.path.isfile(pfx_path):
        return (
            None,
            "Certificado PFX não configurado ou arquivo inexistente. Defina o PFX na empresa ou NFSE_NACIONAL_PFX_PATH no ambiente.",
        )

    cert_paths = _pfx_para_pem_temporarios(pfx_path, pfx_password)
    try:
        last_detail = ""
        forbidden_detail = ""
        for url in urls:
            try:
                r = _requests_get_mtls(
                    url,
                    cert_paths[0],
                    cert_paths[1],
                    verify_ssl=verify_ssl,
                    headers=_headers_get_sefin(),
                )
            except requests.RequestException as e:
                last_detail = str(e)
                if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                    last_detail += (
                        " Dica: rede/firewall ou SEFIN lenta — no servidor defina "
                        "NFSE_NACIONAL_CONNECT_TIMEOUT (ex.: 180), NFSE_NACIONAL_READ_TIMEOUT e NFSE_NACIONAL_HTTP_RETRIES."
                    )
                logger.info("Falha GET %s: %s", url, e)
                continue

            body = r.content or b""
            if r.status_code == 403:
                forbidden_detail = (
                    f"HTTP 403 em {url}: certificado mTLS sem permissão para este recurso "
                    f"(use certificado de prestador, tomador ou intermediário vinculado à NFS-e, "
                    f"conforme manual SEFIN). {(r.text or '')[:300]}"
                )
                last_detail = forbidden_detail
                continue
            if r.status_code != 200:
                js_err = _detalhe_erro_json_resposta_sefin(body)
                if js_err:
                    # A SEFIN usa HTTP 404 com JSON (ex.: E2404) quando não há NFS-e para o id da DPS —
                    # não indica URL errada; o significado está em erro.codigo / erro.descricao.
                    if r.status_code == 404:
                        last_detail = (
                            f"SEFIN: {js_err} "
                            f"(HTTP 404 é o status usado pela API quando o recurso não existe ou não há NFS-e para essa DPS.) "
                            f"Endpoint: {url}"
                        )
                    else:
                        last_detail = f"HTTP {r.status_code} em {url}: {js_err}"
                else:
                    last_detail = f"HTTP {r.status_code} em {url}: {(r.text or '')[:400]}"
                continue

            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except OSError:
                    last_detail = "Resposta compactada em gzip ilegível."
                    continue

            if not _parece_xml_xml(body):
                if json_chave_fallback_base:
                    chave = _extrair_chave_nfse_json(body)
                    if chave:
                        xml2, err2 = baixar_nfse_xml_por_chave(
                            chave,
                            pfx_path,
                            pfx_password,
                            json_chave_fallback_base,
                            verify_ssl=verify_ssl,
                        )
                        if xml2:
                            return xml2, None
                        last_detail = err2 or "Chave obtida na consulta DPS, mas falhou o GET do XML pela chave."
                        continue
                last_detail = (
                    f"Resposta em {url} não parece XML de NFSe (Content-Type: {r.headers.get('Content-Type')}). "
                    f"Prévia: {(body[:200] or b'').decode('utf-8', errors='replace')}"
                )
                continue

            return body, None

        if forbidden_detail and "HTTP 404" in (last_detail or ""):
            return None, forbidden_detail
        if last_detail and "/dps/" in last_detail.lower() and "HTTP 404" in last_detail:
            if "tipoAmbiente=" not in last_detail and "E2404" not in last_detail:
                last_detail += (
                    " Nota: em produção o path é /SefinNacional/dps/... (não /API/SefinNacional/). "
                    "404 sem JSON estruturado pode ser identificador incorreto ou nota ainda não processada."
                )
        return None, last_detail or "Não foi possível obter o XML. Confira identificador/chave, certificado e URL base (homologação x produção)."
    finally:
        for p in cert_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


def montar_identificador_dps(
    codigo_municipio_ibge: str,
    tipo_inscricao_federal: str,
    inscricao_federal_so_digitos: str,
    serie_dps: str,
    numero_dps: str,
) -> str:
    """
    Identificador da DPS (42 dígitos) para GET /dps/{id} na API nacional.
    Igual ao sufixo numérico do atributo ``Id`` de ``infDPS`` (sem o literal ``DPS`` no início):
    IBGE do município emissor (7) + tpInscrFed (1) + inscrição federal (14 dígitos)
    + série DPS (5) + número DPS (15).

    **tpInscrFed (padrão nacional):** ``1`` = CPF (completar inscrição com zeros à esquerda até 14);
    ``2`` = CNPJ.
    """
    ibge = re.sub(r"\D", "", codigo_municipio_ibge or "").zfill(7)[-7:]
    tipo = re.sub(r"\D", "", tipo_inscricao_federal or "")[:1]
    if tipo not in ("1", "2"):
        raise ValueError("Tipo de inscrição federal para o Id da DPS deve ser 1 (CPF) ou 2 (CNPJ).")
    insc = re.sub(r"\D", "", inscricao_federal_so_digitos or "").zfill(14)[-14:]
    serie = re.sub(r"\D", "", serie_dps or "").zfill(5)[-5:]
    num = re.sub(r"\D", "", numero_dps or "").zfill(15)[-15:]
    ident = f"{ibge}{tipo}{insc}{serie}{num}"
    if len(ident) != 42:
        raise ValueError(f"Identificador DPS deve ter 42 dígitos após normalização; obtido {len(ident)}.")
    return ident


def _urls_consulta_nfse_xml(base: str, chave: str) -> list[str]:
    urls: list[str] = []
    for pref in _prefixos_rota_sefin_nacional(base):
        urls.extend(
            [
                f"{base}{pref}/nfse/{chave}",
                f"{base}{pref}/nfse/{chave}/",
                f"{base}{pref}/NFSe/{chave}",
            ]
        )
    return urls


def _urls_consulta_dps_xml(base: str, ident: str) -> list[str]:
    urls: list[str] = []
    for pref in _prefixos_rota_sefin_nacional(base):
        urls.extend(
            [
                f"{base}{pref}/dps/{ident}",
                f"{base}{pref}/dps/{ident}/",
                f"{base}{pref}/DPS/{ident}",
            ]
        )
    return urls


def _urls_consulta_nfse_pdf(base: str, chave: str) -> list[str]:
    urls: list[str] = []
    for pref in _prefixos_rota_sefin_nacional(base):
        urls.extend(
            [
                f"{base}{pref}/nfse/{chave}/pdf",
                f"{base}{pref}/nfse/{chave}/PDF",
                f"{base}{pref}/NFSe/{chave}/pdf",
                f"{base}{pref}/NFSe/{chave}/PDF",
            ]
        )
    return urls


def _urls_consulta_dps_pdf(base: str, ident: str) -> list[str]:
    urls: list[str] = []
    for pref in _prefixos_rota_sefin_nacional(base):
        urls.extend(
            [
                f"{base}{pref}/dps/{ident}/pdf",
                f"{base}{pref}/dps/{ident}/PDF",
                f"{base}{pref}/DPS/{ident}/pdf",
                f"{base}{pref}/DPS/{ident}/PDF",
            ]
        )
    return urls


def baixar_nfse_xml_por_chave(
    chave: str,
    pfx_path: str,
    pfx_password: str,
    base_url: str,
    *,
    verify_ssl: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    GET na API nacional com mTLS. Retorna (xml_bytes, None) ou (None, mensagem_erro).
    """
    chave = normalizar_chave_acesso(chave)
    if len(chave) < 40:
        return None, "Chave de acesso inválida (muito curta). No padrão nacional costuma ter 50 caracteres."

    base, err_base = _base_sefin_ou_erro(base_url)
    if err_base:
        return None, err_base
    urls = _urls_consulta_nfse_xml(base, chave)
    return _baixar_xml_urls_mtls(urls, pfx_path, pfx_password, verify_ssl=verify_ssl)


def _parece_pdf(content: bytes) -> bool:
    return bool(content) and len(content) >= 4 and content[:4] == b"%PDF"


def _baixar_pdf_urls_mtls(
    urls: list[str],
    pfx_path: str,
    pfx_password: str,
    *,
    verify_ssl: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    """GET com mTLS até obter PDF (%PDF)."""
    if not pfx_path or not os.path.isfile(pfx_path):
        return (
            None,
            "Certificado PFX não configurado ou arquivo inexistente.",
        )
    cert_paths = _pfx_para_pem_temporarios(pfx_path, pfx_password)
    try:
        last_detail = ""
        for url in urls:
            try:
                r = _requests_get_mtls(
                    url,
                    cert_paths[0],
                    cert_paths[1],
                    verify_ssl=verify_ssl,
                    headers={"Accept": "application/pdf, */*"},
                )
            except requests.RequestException as e:
                last_detail = str(e)
                if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                    last_detail += (
                        " Dica: NFSE_NACIONAL_CONNECT_TIMEOUT / READ_TIMEOUT / HTTP_RETRIES no ambiente."
                    )
                continue
            body = r.content or b""
            if r.status_code != 200:
                last_detail = f"HTTP {r.status_code} em {url}: {(r.text or '')[:200]}"
                continue
            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except OSError:
                    last_detail = "Resposta gzip ilegível."
                    continue
            if not _parece_pdf(body):
                last_detail = f"Resposta em {url} não é PDF."
                continue
            return body, None
        return None, last_detail or "Não foi possível obter o PDF nas URLs tentadas."
    finally:
        for p in cert_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


def baixar_nfse_pdf_por_chave(
    chave: str,
    pfx_path: str,
    pfx_password: str,
    base_url: str,
    *,
    verify_ssl: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    chave = normalizar_chave_acesso(chave)
    if len(chave) < 40:
        return None, "Chave de acesso inválida para PDF."
    base, err_base = _base_sefin_ou_erro(base_url)
    if err_base:
        return None, err_base
    urls = _urls_consulta_nfse_pdf(base, chave)
    return _baixar_pdf_urls_mtls(urls, pfx_path, pfx_password, verify_ssl=verify_ssl)


def baixar_nfse_pdf_por_identificador_dps(
    identificador_dps: str,
    pfx_path: str,
    pfx_password: str,
    base_url: str,
    *,
    verify_ssl: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    ident = re.sub(r"\s+", "", (identificador_dps or "").strip())
    if len(ident) != 42 or not ident.isdigit():
        return None, "Identificador DPS inválido para PDF."
    base, err_base = _base_sefin_ou_erro(base_url)
    if err_base:
        return None, err_base
    urls = _urls_consulta_dps_pdf(base, ident)
    return _baixar_pdf_urls_mtls(urls, pfx_path, pfx_password, verify_ssl=verify_ssl)


def baixar_nfse_xml_por_identificador_dps(
    identificador_dps: str,
    pfx_path: str,
    pfx_password: str,
    base_url: str,
    *,
    verify_ssl: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Consulta a NFS-e pelo identificador da DPS (emissão feita no portal nacional ou por outro sistema).
    Evita colar a chave de 50 dígitos se você tiver série + número da DPS e o município IBGE do emissor.
    """
    ident = re.sub(r"\s+", "", (identificador_dps or "").strip())
    if len(ident) != 42 or not ident.isdigit():
        return None, "Identificador DPS inválido: informe 42 dígitos (município IBGE + tipo + inscrição + série + número)."

    base, err_base = _base_sefin_ou_erro(base_url)
    if err_base:
        return None, err_base
    urls = _urls_consulta_dps_xml(base, ident)
    return _baixar_xml_urls_mtls(
        urls,
        pfx_path,
        pfx_password,
        verify_ssl=verify_ssl,
        json_chave_fallback_base=base,
    )
