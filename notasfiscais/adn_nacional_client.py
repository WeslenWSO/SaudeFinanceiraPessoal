"""
Cliente ADN (Ambiente de Dados Nacional) para distribuição de documentos NFSe por NSU.

Contrato alinhado ao SDK oficial (nfse-nacional/nfse-php): GET /contribuintes/DFe/{nsu}
com query opcional ``cnpjConsulta`` **somente para CNPJ (14 dígitos)**. Contribuinte PF (CPF):
não enviar esse parâmetro — o certificado mTLS identifica o solicitante (erro E2242 se enviar).
Resposta JSON: LoteDFe, ArquivoXml (gzip+base64), UltimoNSU, MaiorNSU.

Prefixos alternativos podem ser configurados em settings.ADN_NFSE (ex.: ambiente legado).
Requer mTLS com certificado A1 (PFX) como na integração SEFIN.
"""
from __future__ import annotations

import base64
import gzip
import logging
import os
import re
import tempfile
import time
from typing import Any, Optional, Tuple

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

from empresa.nfse_nacional_url import normalizar_base_url_sefin

logger = logging.getLogger(__name__)


def _pfx_para_pem_temporarios(pfx_path: str, pfx_password: str) -> Tuple[str, str]:
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


def _bool(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "sim", "s")
    return bool(v) if v is not None else default


def _json_payload(resp: requests.Response) -> Optional[dict[str, Any]]:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _extrair_ultimo_nsu_obj(obj: Any) -> Optional[int]:
    if isinstance(obj, dict):
        # Itens de lote e respostas genéricas (não usar UltimoNSU/MaiorNSU aqui — só no parser da raiz).
        for k in ("ultimoNsu", "ultNsu", "nsuUltimo", "maxNsu", "maiorNsu", "nsu", "NSU"):
            if k in obj:
                v = obj.get(k)
                try:
                    if v is not None and str(v).strip() != "":
                        return int(str(v))
                except (TypeError, ValueError):
                    pass
        for v in obj.values():
            got = _extrair_ultimo_nsu_obj(v)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for it in obj:
            got = _extrair_ultimo_nsu_obj(it)
            if got is not None:
                return got
    return None


def _decode_xml_payload(raw: Any) -> Optional[bytes]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        data = raw.strip()
        if data.startswith(b"<"):
            return data
        return None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.startswith("<"):
        return text.encode("utf-8")

    try:
        blob = base64.b64decode(text, validate=False)
    except Exception:
        return None
    if not blob:
        return None
    if blob[:2] == b"\x1f\x8b":
        try:
            blob = gzip.decompress(blob)
        except OSError:
            return None
    return blob if blob.lstrip().startswith(b"<") else None


_XML_KEYS = (
    "ArquivoXml",
    "xml",
    "xmlB64",
    "xmlBase64",
    "xmlGzipB64",
    "xmlGzipBase64",
    "xml_gzip_base64",
    "xml_compactado",
    "xmlComprimido",
    "conteudoXml",
    "conteudoXML",
)


def _parece_chave_acesso(v: str) -> Optional[str]:
    d = re.sub(r"\D", "", v or "")
    if len(d) >= 40:
        return d
    return None


def _parse_int_nsu_campos(d: dict[str, Any], *keys: str) -> Optional[int]:
    for k in keys:
        if k not in d:
            continue
        v = d.get(k)
        try:
            if v is not None and str(v).strip() != "":
                return int(str(v))
        except (TypeError, ValueError):
            continue
    return None


def _docs_lote_dfe(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Formato oficial ADN: LoteDFe[].ArquivoXml (gzip+base64), NSU, ChaveAcesso."""
    out: list[dict[str, Any]] = []
    lote = data.get("LoteDFe")
    if not isinstance(lote, list):
        return out
    for it in lote:
        if not isinstance(it, dict):
            continue
        xml_bytes = _decode_xml_payload(it.get("ArquivoXml"))
        if not xml_bytes:
            continue
        nsu = None
        if it.get("NSU") is not None:
            try:
                nsu = int(str(it["NSU"]))
            except (TypeError, ValueError):
                pass
        chave = None
        if it.get("ChaveAcesso"):
            chave = _parece_chave_acesso(str(it["ChaveAcesso"]))
        out.append({"xml_bytes": xml_bytes, "nsu": nsu, "chave": chave})
    return out


def _codigos_erro_adn(data: dict[str, Any]) -> list[str]:
    raw = data.get("Erros") or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for m in raw:
        if isinstance(m, dict) and m.get("Codigo"):
            out.append(str(m["Codigo"]).strip())
    return out


def _mensagens_adn(data: dict[str, Any], chave: str) -> list[str]:
    raw = data.get(chave) or []
    if not isinstance(raw, list):
        return []
    msgs: list[str] = []
    for m in raw:
        if isinstance(m, dict):
            partes = [
                m.get("Codigo"),
                m.get("Descricao") or m.get("descricao"),
                m.get("Mensagem") or m.get("mensagem"),
            ]
            texto = " — ".join(str(p) for p in partes if p)
            if texto:
                msgs.append(texto)
        else:
            msgs.append(str(m))
    return msgs


def _params_consulta_candidates_adn(inscricao_federal_digits: str) -> list[dict[str, str]]:
    """
    Gera candidatos de query para ambientes com variação de regra:
    - CNPJ (14): tenta CNPJ completo, CNPJ base (8) e sem parâmetro.
    - CPF (11): sem parâmetro (certificado mTLS identifica o ator).
    """
    d = re.sub(r"\D", "", inscricao_federal_digits or "")
    if len(d) == 14:
        base8 = d[:8]
        out = [{"cnpjConsulta": d}]
        if base8:
            out.append({"cnpjConsulta": base8})
        out.append({})
        return out
    return [{}]


def _get_adn(
    url: str,
    *,
    cert: Tuple[str, str],
    verify_ssl: bool,
    params: dict[str, str],
    timeout: int,
    max_tentativas: int = 3,
) -> requests.Response:
    """GET com retentativa em 502/503/504 (gateway instável)."""
    last: Optional[requests.Response] = None
    for tentativa in range(max(1, max_tentativas)):
        try:
            r = requests.get(
                url,
                params=params if params else None,
                cert=cert,
                timeout=timeout,
                verify=verify_ssl,
                headers={"Accept": "application/json"},
            )
        except requests.exceptions.SSLError as e:
            msg = str(e)
            if verify_ssl and ("CERTIFICATE_VERIFY_FAILED" in msg or "Hostname mismatch" in msg):
                raise requests.RequestException(
                    "Falha SSL no ADN (certificado do servidor incompatível com o host). "
                    "Configure ADN_NFSE_VERIFY_SSL=false para este ambiente e reinicie o servidor."
                ) from e
            raise
        except requests.RequestException as e:
            msg = str(e)
            if "NameResolutionError" in msg or "Failed to resolve" in msg or "getaddrinfo failed" in msg:
                raise requests.RequestException(
                    "Falha de DNS ao acessar o ADN (não foi possível resolver adn.nfse.gov.br). "
                    "Verifique internet, DNS/rede corporativa/VPN e tente novamente em alguns minutos."
                ) from e
            raise
        last = r
        if r.status_code in (502, 503, 504) and tentativa < max_tentativas - 1:
            time.sleep(1.0 * (tentativa + 1))
            continue
        return r
    assert last is not None
    return last


def _extrair_docs_obj(obj: Any) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if "LoteDFe" in obj:
            dfe = _docs_lote_dfe(obj)
            if dfe:
                return dfe
            if isinstance(obj.get("LoteDFe"), list):
                return []
        xml_bytes = None
        for k in _XML_KEYS:
            if k in obj:
                xml_bytes = _decode_xml_payload(obj.get(k))
                if xml_bytes:
                    break
        if xml_bytes:
            nsu = _extrair_ultimo_nsu_obj(obj)
            chave = None
            for k, v in obj.items():
                lk = str(k).lower()
                if "chave" in lk and isinstance(v, str):
                    chave = _parece_chave_acesso(v)
                    if chave:
                        break
            docs.append({"xml_bytes": xml_bytes, "nsu": nsu, "chave": chave})
        for v in obj.values():
            docs.extend(_extrair_docs_obj(v))
    elif isinstance(obj, list):
        for it in obj:
            docs.extend(_extrair_docs_obj(it))
    return docs


def _normalizar_prefixos_dfe(paths: Any, fallback: list[str]) -> list[str]:
    out: list[str] = []
    items = paths if isinstance(paths, list) else fallback
    for p in items:
        s = str(p or "").strip()
        if not s:
            continue
        if not s.startswith("/"):
            s = "/" + s
        out.append(s)
    return out or fallback


def _montar_url_dfe(base: str, prefix: str, nsu: int) -> str:
    p = (prefix or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    if "{nsu}" in p:
        return f"{base}{p.format(nsu=int(nsu))}"
    return f"{base}{p.rstrip('/')}/{int(nsu)}"


def consultar_ultimo_nsu_adn(
    *,
    base_url: str,
    pfx_path: str,
    pfx_password: str,
    cnpj: str,
    verify_ssl: bool = True,
    ultimo_nsu_paths: Optional[list[str]] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Obtém MaiorNSU (ou UltimoNSU) com uma consulta GET /contribuintes/DFe/0 — não existe endpoint /ultimo-nsu.
    """
    if not pfx_path or not os.path.isfile(pfx_path):
        return None, "Certificado PFX não configurado para consultar último NSU no ADN."
    base = normalizar_base_url_sefin(base_url or "")
    if not base:
        return None, "URL base do ADN vazia."
    prefixos = _normalizar_prefixos_dfe(
        ultimo_nsu_paths,
        ["/contribuintes/DFe"],
    )
    cert_paths = _pfx_para_pem_temporarios(pfx_path, pfx_password)
    cert = (cert_paths[0], cert_paths[1])
    try:
        last_err = ""
        cnpj_digits = re.sub(r"\D", "", cnpj or "")
        params_candidates = _params_consulta_candidates_adn(cnpj_digits)
        for prefix in prefixos:
            url = _montar_url_dfe(base, prefix, 0)
            for use_params in params_candidates:
                try:
                    r = _get_adn(
                        url,
                        cert=cert,
                        verify_ssl=verify_ssl,
                        params=use_params,
                        timeout=60,
                    )
                except requests.RequestException as e:
                    last_err = str(e)
                    break
                data = _json_payload(r)
                if (
                    isinstance(data, dict)
                    and r.status_code == 400
                    and "E2242" in _codigos_erro_adn(data)
                ):
                    continue
                if r.status_code != 200 or not isinstance(data, dict):
                    txt = (r.text or "")[:220]
                    last_err = f"HTTP {r.status_code} em {url}: {txt}"
                    break
                erros = _mensagens_adn(data, "Erros")
                if erros:
                    last_err = "; ".join(erros[:3])
                    break
                got = _parse_int_nsu_campos(data, "MaiorNSU", "UltimoNSU", "maiorNsu", "ultimoNsu", "ultNsu")
                if got is not None:
                    return got, None
                last_err = f"Resposta 200 em {url}, mas sem MaiorNSU/UltimoNSU."
                break
        return None, last_err or "Não foi possível consultar o último NSU no ADN."
    finally:
        for p in cert_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


def distribuir_documentos_adn(
    *,
    base_url: str,
    pfx_path: str,
    pfx_password: str,
    cnpj: str,
    ultimo_nsu: int,
    verify_ssl: bool = True,
    distribuicao_paths: Optional[list[str]] = None,
    max_documentos: int = 200,
    max_paginas: int = 60,
) -> Tuple[dict[str, Any], Optional[str]]:
    """
    Distribui documentos NFSe a partir do NSU informado (GET /contribuintes/DFe/{nsu}).
    Retorna dict com `documentos`, `ultimo_nsu` e `tem_mais`.
    """
    if not pfx_path or not os.path.isfile(pfx_path):
        return {}, "Certificado PFX não configurado para distribuição ADN."
    base = normalizar_base_url_sefin(base_url or "")
    if not base:
        return {}, "URL base do ADN vazia."
    prefixos = _normalizar_prefixos_dfe(
        distribuicao_paths,
        ["/contribuintes/DFe"],
    )
    cnpj_digits = re.sub(r"\D", "", cnpj or "")
    if len(cnpj_digits) not in (11, 14):
        return {}, "CNPJ/CPF da empresa inválido para distribuição ADN."

    cert_paths = _pfx_para_pem_temporarios(pfx_path, pfx_password)
    try:
        todos_docs: list[dict[str, Any]] = []
        nsu_cursor = int(ultimo_nsu or 0)
        tem_mais = False
        origem_url = ""
        last_err = ""
        params_candidates = _params_consulta_candidates_adn(cnpj_digits)
        cert = (cert_paths[0], cert_paths[1])

        paginas_sem_novidade = 0
        for _page in range(max(1, int(max_paginas or 1))):
            cursor_antes = nsu_cursor
            resposta_data: Optional[dict[str, Any]] = None
            response_url = ""

            for prefix in prefixos:
                url = _montar_url_dfe(base, prefix, nsu_cursor)
                for use_params in params_candidates:
                    try:
                        r = _get_adn(
                            url,
                            cert=cert,
                            verify_ssl=verify_ssl,
                            params=use_params,
                            timeout=90,
                        )
                    except requests.RequestException as e:
                        last_err = str(e)
                        break
                    data = _json_payload(r)
                    if (
                        isinstance(data, dict)
                        and r.status_code == 400
                        and "E2242" in _codigos_erro_adn(data)
                    ):
                        continue
                    if r.status_code == 200 and isinstance(data, dict):
                        resposta_data = data
                        response_url = r.url
                        origem_url = response_url or url
                        break
                    # E2220 = fim da fila para o NSU informado (não é erro fatal).
                    if (
                        isinstance(data, dict)
                        and r.status_code == 404
                        and "E2220" in _codigos_erro_adn(data)
                    ):
                        resposta_data = data
                        response_url = r.url
                        origem_url = response_url or url
                        break
                    txt = (r.text or "")[:240]
                    last_err = f"HTTP {r.status_code} em {url}: {txt}"
                if resposta_data:
                    break

            if not resposta_data:
                if todos_docs:
                    break
                return {}, (last_err or "Falha ao consultar distribuição ADN (GET /contribuintes/DFe/{nsu}).")

            erros = _mensagens_adn(resposta_data, "Erros")
            codigos = _codigos_erro_adn(resposta_data)
            # E2220 (nenhum documento localizado a partir do NSU) encerra ciclo normalmente.
            if "E2220" in codigos:
                break
            if erros:
                return {}, "ADN: " + "; ".join(erros[:5])

            docs = _extrair_docs_obj(resposta_data)
            vistos: set[bytes] = set()
            dedup_docs: list[dict[str, Any]] = []
            for d in docs:
                key = d["xml_bytes"][:120]
                if key in vistos:
                    continue
                vistos.add(key)
                dedup_docs.append(d)

            todos_docs.extend(dedup_docs)

            ultimo_resp = _parse_int_nsu_campos(resposta_data, "UltimoNSU", "ultimoNsu", "ultNsu")
            maior_resp = _parse_int_nsu_campos(resposta_data, "MaiorNSU", "maiorNsu", "maxNsu")

            if ultimo_resp is not None:
                nsu_cursor = ultimo_resp
            elif dedup_docs:
                nsus = [d["nsu"] for d in dedup_docs if d.get("nsu") is not None]
                if nsus:
                    nsu_cursor = max(nsus)

            tem_mais = bool(
                maior_resp is not None
                and ultimo_resp is not None
                and ultimo_resp < maior_resp
                and len(todos_docs) < max_documentos
            )
            if "temMais" in resposta_data:
                tem_mais = tem_mais or _bool(resposta_data.get("temMais"), default=False)
            if "haMais" in resposta_data:
                tem_mais = tem_mais or _bool(resposta_data.get("haMais"), default=False)

            if len(todos_docs) >= max_documentos:
                break
            # Alguns ambientes não retornam flag "temMais"/"haMais" de forma confiável.
            # Nesses casos, seguimos enquanto houver progresso de NSU ou novos docs no lote.
            houve_novidade = bool(dedup_docs) or (nsu_cursor > cursor_antes)
            if houve_novidade:
                paginas_sem_novidade = 0
                if tem_mais or (nsu_cursor > cursor_antes) or dedup_docs:
                    continue
            else:
                paginas_sem_novidade += 1
            if paginas_sem_novidade >= 1:
                break

        return {
            "documentos": todos_docs[:max_documentos],
            "ultimo_nsu": nsu_cursor,
            "tem_mais": bool(tem_mais),
            "origem_url": origem_url,
        }, None
    finally:
        for p in cert_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
