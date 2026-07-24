"""
Lista certificados do repositório Windows (Personal / 'My') cujo Subject/SAN
contém o CNPJ informado (14 dígitos). Usa certutil.exe (nativo do Windows).

Disponível apenas em sys.platform == 'win32'. Não exporta chave privada.
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


def limpar_cnpj(cnpj: str | None) -> str:
    if not cnpj:
        return ""
    return re.sub(r"\D", "", str(cnpj).strip())[:14]


def _cnpj_no_texto(texto: str, cnpj14: str) -> bool:
    """True se os 14 dígitos do CNPJ aparecem como substring nos dígitos do texto (máscaras variadas)."""
    if len(cnpj14) != 14:
        return False
    digitos = re.sub(r"\D", "", texto)
    return cnpj14 in digitos


def _parse_blocos_certutil(stdout: str) -> list[str]:
    """Divide a saída do certutil em um bloco por certificado."""
    markers = list(
        re.finditer(r"={10,}\s*(?:Certificate|Certificado)\s+\d+\s*={10,}", stdout, re.IGNORECASE)
    )
    if markers:
        blocos: list[str] = []
        for i, m in enumerate(markers):
            ini = m.start()
            fim = markers[i + 1].start() if i + 1 < len(markers) else len(stdout)
            chunk = stdout[ini:fim].strip()
            if chunk:
                blocos.append(chunk)
        return blocos
    partes = re.split(r"={5,}\s*Certificate\s+\d+\s*={5,}", stdout, flags=re.IGNORECASE)
    if len(partes) <= 1:
        partes = re.split(r"={5,}\s*Certificado\s+\d+\s*={5,}", stdout, flags=re.IGNORECASE)
    blocos = [p.strip() for p in partes if p.strip()]
    if len(blocos) <= 1 and re.search(r"(?:Subject|Assunto)\s*:", stdout, re.I):
        return [stdout.strip()]
    return blocos


def _extrair_campo(bloco: str, *nomes: str) -> str:
    """Primeira linha 'Nome: valor' encontrada dentre nomes possíveis (case insensitive)."""
    for linha in bloco.splitlines():
        m = re.match(r"^\s*([^:]+):\s*(.*)$", linha)
        if not m:
            continue
        chave = m.group(1).strip().lower()
        valor = m.group(2).strip()
        for nome in nomes:
            if chave == nome.lower():
                return valor
    return ""


def _extrair_thumbprint(bloco: str) -> str:
    """SHA1 em hex sem espaços."""
    for padrao in (
        r"Cert(?:ificate)?\s+Hash\(sha1\)\s*:\s*([0-9a-fA-F\s]+)",
        r"Hash\s*\(?sha1\)?\s*:\s*([0-9a-fA-F\s]+)",
        r"Cert Hash\(sha1\)\s*:\s*([0-9a-fA-F\s]+)",
    ):
        m = re.search(padrao, bloco, re.IGNORECASE)
        if m:
            hx = re.sub(r"\s+", "", m.group(1))
            if len(hx) >= 40:
                return hx[:40].upper()
    # fallback: última linha típica de thumbprint
    m = re.search(r"([0-9a-f]{2}(?:\s+[0-9a-f]{2}){19})", bloco, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    return ""


def _listar_my_certutil(cnpj14: str, *, usuario_atual: bool) -> list[dict[str, Any]]:
    """
    usuario_atual=True -> -user -store My (certificados do usuário logado).
    usuario_atual=False -> -store My (repositório do computador / máquina local).
    """
    cmd = ["certutil", "-user", "-store", "My"] if usuario_atual else ["certutil", "-store", "My"]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        logger.warning("certutil não encontrado no PATH")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("certutil timeout ao listar store My")
        return []

    if proc.returncode != 0 and not (proc.stdout or "").strip():
        logger.info("certutil retorno %s stderr=%s", proc.returncode, (proc.stderr or "")[:500])
        return []

    texto = proc.stdout or ""
    encontrados: list[dict[str, Any]] = []
    repositorio = "Usuario atual (Personal)" if usuario_atual else "Computador local (Personal)"

    for bloco in _parse_blocos_certutil(texto):
        subject = _extrair_campo(
            bloco,
            "Subject",
            "Assunto",
            "Subject Name",
        )
        if not subject or not _cnpj_no_texto(subject, cnpj14):
            continue
        issuer = _extrair_campo(bloco, "Issuer", "Emissor")
        not_after = _extrair_campo(
            bloco,
            "NotAfter",
            "Not After",
            "Não após",
            "Data de validade",
            "Validade",
        )
        serial = _extrair_campo(bloco, "Serial Number", "Número de série", "Serial")
        thumb = _extrair_thumbprint(bloco)
        encontrados.append(
            {
                "repositorio": repositorio,
                "subject": subject,
                "issuer": issuer,
                "validade_fim": not_after,
                "serial": serial,
                "thumbprint_sha1": thumb,
            }
        )

    return encontrados


def listar_certificados_windows_por_cnpj(cnpj: str | None) -> list[dict[str, Any]]:
    """
    Retorna lista de dicts com metadados públicos dos certificados cujo Subject
    contém o CNPJ (14 dígitos). Consulta loja Personal do usuário e do computador.

    Fora do Windows retorna lista vazia.
    """
    cnpj14 = limpar_cnpj(cnpj)
    if len(cnpj14) != 14:
        return []
    if sys.platform != "win32":
        return []

    vistos: set[str] = set()
    saida: list[dict[str, Any]] = []
    for usuario in (True, False):
        for item in _listar_my_certutil(cnpj14, usuario_atual=usuario):
            chave = item.get("thumbprint_sha1") or f"{item.get('serial')}|{item.get('subject')}"
            if chave in vistos:
                continue
            vistos.add(chave)
            saida.append(item)
    return saida
