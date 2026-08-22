from django.db import transaction, IntegrityError
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Tuple
import unicodedata
import xml.etree.ElementTree as ET
import re
from dateutil import parser as date_parser
import traceback
import logging
import os

from django.conf import settings as django_settings

from .models import NotaFiscalServico
from socio.models import Socio

logger = logging.getLogger(__name__)


def _extrair_nome_medico_da_discriminacao(discriminacao: str) -> Optional[str]:
    """
    Extrai o nome do médico quando a discriminação contém 'Dr.' ou 'Dra.'.
    Retorna o nome normalizado ou None se não encontrar padrão.
    """
    if not discriminacao or not discriminacao.strip():
        return None
    padrao = re.compile(
        r'\bD[rR]a?\.?\s+([A-Za-zÀ-ÿ\s]+?)(?=\s*[-–—]\s*|\s+CRM\s*:|\s+ESPECIALISTA\b|\s+DATA\s*:|\s*FORMA\s+DE\s+PAGAMENTO|$)',
        re.IGNORECASE
    )
    m = padrao.search(discriminacao)
    if not m:
        return None
    nome = m.group(1).strip()
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome if len(nome) >= 2 else None


def _nome_socio_completo(s) -> str:
    """Retorna o nome completo do sócio (socio + lastname) normalizado para comparação."""
    parte1 = (getattr(s, 'socio', None) or '').strip()
    parte2 = (getattr(s, 'lastname', None) or '').strip()
    return re.sub(r'\s+', ' ', f'{parte1} {parte2}'.strip()).lower()


def extrair_socio(discriminacao: str, socios_queryset) -> Optional[Socio]:
    """
    Vincula um Sócio ao texto da discriminação (Dr./Dra. ou fallback por nome no texto).
    Apenas sócios já cadastrados são considerados.
    """
    if not discriminacao:
        return None
    texto = discriminacao.lower()
    socios_list = list(socios_queryset)

    nome_extraido = _extrair_nome_medico_da_discriminacao(discriminacao)
    if nome_extraido:
        nome_extraido_norm = re.sub(r'\s+', ' ', nome_extraido.strip()).lower()
        partes_extraido = nome_extraido_norm.split()
        primeiro_nome_extraido = partes_extraido[0] if partes_extraido else ""
        for s in socios_list:
            nome_completo = _nome_socio_completo(s)
            if not nome_completo:
                continue
            if nome_extraido_norm in nome_completo or nome_completo in nome_extraido_norm:
                return s
            partes_socio = set(p for p in nome_completo.split() if len(p) >= 2)
            partes_extraido_set = set(p for p in partes_extraido if len(p) >= 2)
            intersec = partes_extraido_set & partes_socio
            # Exige que o primeiro nome esteja na interseção para evitar match só por "de"/"oliveira"
            if intersec and len(intersec) >= 2 and primeiro_nome_extraido in intersec:
                return s
            primeiro_nome_socio = nome_completo.split()[0] if nome_completo.split() else ""
            if primeiro_nome_extraido and primeiro_nome_socio and primeiro_nome_extraido == primeiro_nome_socio:
                return s

    candidatos = []
    for s in socios_list:
        nome = (getattr(s, 'socio', None) or "").strip()
        if not nome:
            continue
        partes = [p for p in re.split(r'\s+', nome) if len(p) >= 3]
        if nome.lower() in texto:
            candidatos.append((len(nome), s))
            continue
        score = sum(1 for p in partes if p.lower() in texto)
        if score:
            candidatos.append((score, s))
    if not candidatos:
        return None
    candidatos.sort(key=lambda t: t[0], reverse=True)
    return candidatos[0][1]


# #region agent log
def _debug_nfse_log(location, message, data, hypothesis_id):
    try:
        import json
        import time
        with open("debug-2af46d.log", "a", encoding="utf-8") as f:
            payload = {"sessionId": "2af46d", "location": location, "message": message, "data": data, "hypothesisId": hypothesis_id, "timestamp": int(time.time() * 1000)}
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion


def _nfs_import_debug_log(level, msg, *args, **kwargs):
    """Emite log apenas quando NFS_IMPORT_DEBUG está ativo (evita poluir produção)."""
    if getattr(django_settings, "NFS_IMPORT_DEBUG", False):
        getattr(logger, level)(msg, *args, **kwargs)

def safe_print(*args, **kwargs):
    """Print function that handles encoding errors safely"""
    try:
        print(*args, **kwargs)
    except (OSError, UnicodeEncodeError) as e:
        # Fallback to logging if print fails
        logger.error(f"Print failed: {e}")
        try:
            # Try to print with error replacement
            safe_args = []
            for arg in args:
                if isinstance(arg, str):
                    safe_args.append(arg.encode('utf-8', errors='replace').decode('utf-8'))
                else:
                    safe_args.append(str(arg).encode('utf-8', errors='replace').decode('utf-8'))
            print(*safe_args, **kwargs)
        except:
            # Last resort: use repr
            print(repr(args), repr(kwargs))

def safe_traceback_print_exc():
    """Safely print traceback, handling encoding issues"""
    try:
        traceback.print_exc()
    except (OSError, UnicodeEncodeError) as e:
        logger.error(f"Traceback print failed: {e}")
        try:
            # Try to get traceback as string and print safely
            import io
            import sys
            string_io = io.StringIO()
            traceback.print_exc(file=string_io)
            tb_str = string_io.getvalue()
            safe_print("TRACEBACK:", tb_str.encode('utf-8', errors='replace').decode('utf-8'))
        except:
            safe_print("Failed to print traceback safely")

def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1].lower() if tag else ''

# Namespace SPED NFSe (Portal Nacional)
NS_SPED = "http://www.sped.fazenda.gov.br/nfse"


def _qname(ns: str, local: str) -> str:
    """Tag com namespace no formato do ElementTree."""
    return "{%s}%s" % (ns, local) if ns else local


def _find_ns(root, path: str, ns: str):
    """Busca elemento por caminho com namespace. path ex: 'DPS/infDPS/serie'."""
    if not root or not path:
        return None
    el = root
    for segment in path.strip("/").split("/"):
        segment = segment.strip()
        if not segment:
            continue
        tag = _qname(ns, segment)
        next_el = el.find(tag) if el is not None else None
        if next_el is None and el is not None:
            next_el = el.find(".//%s" % tag)
        el = next_el
        if el is None:
            return None
    return el


def _t(root, path: str, ns: str = NS_SPED) -> str:
    """Retorna texto do primeiro elemento encontrado no caminho (com namespace)."""
    el = _find_ns(root, path, ns)
    if el is None:
        return ""
    return (el.text or "").strip()


def _d(root, path: str, ns: str = NS_SPED):
    """Retorna date a partir do texto no caminho (ISO 8601)."""
    text = _t(root, path, ns)
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
        return parsed.date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            s = text.replace("Z", "+00:00")[:19]
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            continue
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    logger.warning("Não foi possível converter data SPED: %s", text[:50])
    return None


def _dec(root, path: str, ns: str = NS_SPED) -> "Decimal":
    """Retorna Decimal a partir do texto no caminho; 0 se vazio ou inválido."""
    text = _t(root, path, ns)
    if not text:
        return Decimal("0")
    try:
        return Decimal(text.replace(",", "."))
    except Exception:
        return Decimal("0")


def _dec_primeiro(root, paths, ns: str = NS_SPED) -> Decimal:
    for path in paths:
        val = _dec(root, path, ns)
        if val > 0:
            return val
    return Decimal("0")


def _t_primeiro(root, paths, ns: str = NS_SPED) -> str:
    for path in paths:
        val = _t(root, path, ns)
        if val:
            return val
    return ""


def _ler_conteudo_xml(xml_file) -> bytes:
    if isinstance(xml_file, (bytes, bytearray)):
        return bytes(xml_file)
    if hasattr(xml_file, "read"):
        if hasattr(xml_file, "seek"):
            xml_file.seek(0)
        data = xml_file.read() or b""
        if hasattr(xml_file, "seek"):
            xml_file.seek(0)
        return data
    return b""


def _conteudo_xml_vazio(xml_file) -> bool:
    """True se o arquivo não tem conteúdo XML utilizável."""
    data = _ler_conteudo_xml(xml_file)
    if not data or not data.strip():
        return True
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    texto = data.decode("utf-8", errors="replace").strip()
    return not texto


def preview_arquivo_vazio(nome_arquivo: str) -> dict:
    """Entrada de preview para um XML vazio (importação em lote)."""
    base = os.path.basename(nome_arquivo) or nome_arquivo or "arquivo.xml"
    return {
        "numero_nota": base,
        "serie": "—",
        "data_emissao": "",
        "valor_bruto": Decimal("0"),
        "valor_liquido": Decimal("0"),
        "cliente": "Arquivo vazio",
        "cnpj_cpf": "",
        "discriminacao": "",
        "cnpj_prestador": "",
        "cnpj_valido": False,
        "status": "invalido",
        "motivo": "Arquivo vazio",
        "arquivo": nome_arquivo,
    }


def resultado_importacao_arquivo_vazio(nome_arquivo: str) -> dict:
    """Resultado de importação quando o XML está vazio (não interrompe o lote)."""
    base = os.path.basename(nome_arquivo) or nome_arquivo or "nota.xml"
    return {
        "nfses": [],
        "notas_importadas": [],
        "notas_ignoradas": [{
            "numero_nota": base,
            "cliente": nome_arquivo,
            "motivo": f"Arquivo vazio: {nome_arquivo}",
        }],
        "total_processadas": 0,
        "total_importadas": 0,
        "total_ignoradas": 1,
        "arquivo_vazio": True,
    }


def _parse_xml_root(xml_file):
    """Lê bytes do arquivo, valida conteúdo e retorna elemento raiz."""
    data = _ler_conteudo_xml(xml_file)
    if not data or not data.strip():
        raise ValueError(
            "Arquivo XML vazio ou inválido. Selecione um arquivo NFSe (.xml) com conteúdo."
        )
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    texto = data.decode("utf-8", errors="replace").strip()
    if not texto:
        raise ValueError("Arquivo XML vazio ou inválido.")
    if not texto.lstrip().startswith("<"):
        raise ValueError('Arquivo não parece ser XML válido (conteúdo não inicia com "<").')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Erro ao processar XML: {exc}") from exc


def _extrair_ibscbs_sped(infnfse_elem) -> dict:
    """Extrai IBS/CBS do layout NFSe nacional (reforma tributária / RTC)."""
    base_ibs_cbs = _dec_primeiro(infnfse_elem, [
        "IBSCBS/vBC",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBS/vBC",
        "DPS/infDPS/IBSCBS/valores/vBC",
    ])
    valor_ibs = _dec_primeiro(infnfse_elem, [
        "IBSCBS/totCIBS/vIBSTot",
        "IBSCBS/vIBS",
        "IBSCBS/gIBSCBS/vIBS",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBS/vIBS",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBSAjuste/vIBS",
        "IBSCBS/totCIBS/gTribSN/vIBSSN",
    ])
    if valor_ibs <= 0:
        v_ibs_uf = _dec(infnfse_elem, "IBSCBS/gIBSCBS/gIBSUF/vIBSUF", NS_SPED)
        v_ibs_mun = _dec(infnfse_elem, "IBSCBS/gIBSCBS/gIBSMun/vIBSMun", NS_SPED)
        if v_ibs_uf > 0 or v_ibs_mun > 0:
            valor_ibs = v_ibs_uf + v_ibs_mun
    valor_cbs = _dec_primeiro(infnfse_elem, [
        "IBSCBS/totCIBS/vCBSTot",
        "IBSCBS/vCBS",
        "IBSCBS/gIBSCBS/gCBS/vCBS",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBS/gCBS/vCBS",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBSAjuste/vCBS",
        "IBSCBS/totCIBS/gTribSN/vCBSSN",
    ])
    aliquota_ibs = _dec_primeiro(infnfse_elem, [
        "IBSCBS/totCIBS/pAliqIBS",
        "IBSCBS/gIBSCBS/gIBSUF/pIBSUF",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBS/gIBSUF/pIBSUF",
    ])
    aliquota_cbs = _dec_primeiro(infnfse_elem, [
        "IBSCBS/totCIBS/pAliqCBS",
        "IBSCBS/gIBSCBS/gCBS/pCBS",
        "DPS/infDPS/IBSCBS/valores/trib/gIBSCBS/gCBS/pCBS",
    ])
    return {
        "base_ibs_cbs": base_ibs_cbs,
        "valor_ibs": valor_ibs,
        "valor_cbs": valor_cbs,
        "aliquota_ibs": aliquota_ibs,
        "aliquota_cbs": aliquota_cbs,
    }


def _kwargs_ibscbs_nfse(ibscbs: dict, *, zerar: bool = False) -> dict:
    zero = Decimal("0")
    if zerar:
        return {
            "base_ibs_cbs": zero,
            "valor_ibs": zero,
            "valor_cbs": zero,
            "aliquota_ibs": zero,
            "aliquota_cbs": zero,
        }
    return {
        "base_ibs_cbs": ibscbs.get("base_ibs_cbs") or zero,
        "valor_ibs": ibscbs.get("valor_ibs") or zero,
        "valor_cbs": ibscbs.get("valor_cbs") or zero,
        "aliquota_ibs": ibscbs.get("aliquota_ibs") or zero,
        "aliquota_cbs": ibscbs.get("aliquota_cbs") or zero,
    }


def _ibscbs_proporcional(ibscbs_kwargs: dict, proporcao: Decimal) -> dict:
    zero = Decimal("0")
    prop = proporcao if proporcao else Decimal("1")
    return {
        "base_ibs_cbs": (ibscbs_kwargs.get("base_ibs_cbs") or zero) * prop,
        "valor_ibs": (ibscbs_kwargs.get("valor_ibs") or zero) * prop,
        "valor_cbs": (ibscbs_kwargs.get("valor_cbs") or zero) * prop,
        "aliquota_ibs": ibscbs_kwargs.get("aliquota_ibs") or zero,
        "aliquota_cbs": ibscbs_kwargs.get("aliquota_cbs") or zero,
    }


def _is_nfse_sped(root) -> bool:
    """Verifica se o root é NFSe do Portal Nacional (SPED)."""
    if root is None:
        return False
    local = _local(root.tag)
    if local != "nfse":
        return False
    uri = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    return uri == NS_SPED


# --- Forma de pagamento (extração e vínculo com Cobranca) --------------------

def _normalizar_texto(s: str) -> str:
    """Lowercase e remove acentos para comparação flexível."""
    if not s:
        return ""
    s = (s or "").strip().lower()
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


# Padrões de texto que indicam uma única forma de pagamento (extrair_forma_pagamento).
PAGAMENTOS_PADROES = [
    "pix", "cartão debito", "cartao debito", "cartao credito", "cartão credito",
    "dh", "dinheiro", "especie", "espécie", "boleto", "transferência", "transferencia",
    "depósito", "deposito", "convênio", "convenio", "cheque", "ted", "doc",
    "cc", "credito", "debito",
]


def _sanear_fragmento_apos_forma_pagamento_colon(fragment: str) -> str:
    """
    Remove prefixo numérico antes do rótulo (ex.: prefeitura 'FORMA DE PAGAMENTO:600 PIX').
    """
    t = (fragment or "").strip()
    if not t:
        return ""
    t2 = re.sub(r"^\d+[\s.\-:_/\\]*", "", t, flags=re.IGNORECASE).strip()
    return t2 if t2 else t


def _remover_valor_moeda_no_inicio(fragment: str) -> str:
    """Remove valor em R$ no início do fragmento (ex.: '480,00 CD' -> 'CD')."""
    t = (fragment or "").strip()
    if not t:
        return ""
    # 1.234,56 ou 480,00 (vírgula decimal brasileira)
    t2 = re.sub(r"^\d{1,3}(?:\.\d{3})*,\d{2}\s+", "", t, count=1).strip()
    if t2 != t:
        return t2
    t3 = re.sub(r"^\d+,\d{2}\s+", "", t, count=1).strip()
    if t3 != t:
        return t3
    return t


def extrair_forma_pagamento(discriminacao: str) -> Optional[str]:
    """
    Identifica a forma de pagamento por palavra-chave na discriminação.
    Retorna string normalizada (ex.: 'PIX', 'CARTAO DEBITO') ou None.
    """
    # #region agent log
    _debug_nfse_log("extrair_forma_pagamento:entry", "extrair_forma_pagamento called", {"discriminacao_len": len(discriminacao or ""), "discriminacao_snippet": (discriminacao or "")[:200]}, "A")
    # #endregion
    if not discriminacao:
        return None
    texto = _normalizar_texto(discriminacao)
    # #region agent log
    _debug_nfse_log("extrair_forma_pagamento:texto", "texto after _normalizar_texto", {"texto_snippet": texto[:200], "has_debito": "debito" in texto}, "A")
    # #endregion

    # "PAGAMENTO: CD" / "PAGAMENTO: CC" (sem "FORMA DE ") -> CARTAO DEBITO / CARTAO CREDITO
    pagamento_cd_cc = re.search(r"pagamento\s*:\s*(CD|CC)\b", texto, re.IGNORECASE)
    if pagamento_cd_cc:
        sigla = pagamento_cd_cc.group(1).upper()
        return "CARTAO DEBITO" if sigla == "CD" else "CARTAO CREDITO"

    # Prioridade: "FORMA DE PAGAMENTO  CD", "FORMA DE PAGAMENTO (CD)", etc. (aceita um ou mais espaços)
    forma_cd_cc = re.search(r"forma\s+de\s+pagamento\s+(CD|CC)\b", texto, re.IGNORECASE)
    if forma_cd_cc:
        sigla = forma_cd_cc.group(1).upper()
        return "CARTAO DEBITO" if sigla == "CD" else "CARTAO CREDITO"

    # Prioridade: "FORMA DE PAGAMENTO (CD)", "FORMA DE PAGAMENTO P(CD)", "FORMA DE PAGAMENTO (CC)", etc.
    forma_parenteses = re.search(r"forma\s+de\s+pagamento\s*P?\s*\(\s*([A-Za-z]+)\s*\)", texto, re.IGNORECASE)
    if forma_parenteses:
        sigla = forma_parenteses.group(1).strip().upper()
        mapa = {"CD": "CARTAO DEBITO", "CC": "CARTAO CREDITO", "PIX": "PIX", "DH": "DINHEIRO", "DINHEIRO": "DINHEIRO", "ESPECIE": "DINHEIRO", "BOLETO": "BOLETO", "TED": "TED", "DOC": "DOC", "TRANSFERENCIA": "TRANSFERENCIA"}
        if sigla in mapa:
            return mapa[sigla]

    # "FORMA DE PAGAMENTO: 600 PIX" / ":17pix" — código numérico opcional antes do rótulo
    if re.search(r"forma\s+de\s+pagamento\s*:\s*(?:\d+[.\s\-/_]*)?pix\b", texto):
        return "PIX"
    if re.search(
        r"forma\s+de\s+pagamento\s*:\s*(?:\d+[.\s\-/_]*)?(dinheiro|dh|especie)\b",
        texto,
    ):
        return "DINHEIRO"

    # "FORMA DE PAGAMENTO:480,00 CD" — valor com vírgula antes de CD/CC (evita capturar só "480" e cair em heurísticas erradas)
    if re.search(
        r"forma\s+de\s+pagamento\s*:\s*(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*cd\b",
        texto,
    ):
        return "CARTAO DEBITO"
    if re.search(
        r"forma\s+de\s+pagamento\s*:\s*(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*cc\b",
        texto,
    ):
        return "CARTAO CREDITO"

    # Primeira prioridade: extrair o trecho após "forma de pagamento:" até o fim da linha (vírgula em valores não corta)
    forma_match = re.search(r"forma\s+de\s+pagamento\s*:\s*([^\n]+)", texto, re.IGNORECASE)
    if forma_match:
        raw = forma_match.group(1).strip()
        # "débito, AUT: ..." — vírgula separa forma de outro campo; não cortar "480,00"
        m_outro = re.search(r",\s*[A-Za-z]{2,}\s*:", raw)
        if m_outro and not re.match(r"^\d{1,3}(?:\.\d{3})*,\d{2}", raw[: m_outro.start()].strip()):
            raw = raw[: m_outro.start()].strip()
        elif m_outro:
            antes = raw[: m_outro.start()].rstrip()
            if not re.search(r",\d{2}\s*$", antes):
                raw = antes
        raw = _remover_valor_moeda_no_inicio(raw)
        sane = _sanear_fragmento_apos_forma_pagamento_colon(raw)
        palavra = _normalizar_texto(sane)
        partes = palavra.split() if palavra else []
        # "600 PIX" / "17 PIX": prioriza token explícito (evita cair só em código desconhecido)
        if "pix" in partes:
            return "PIX"
        if any(p in ("dinheiro", "dh", "especie") for p in partes):
            return "DINHEIRO"
        if "cd" in partes or palavra.endswith(" cd") or palavra == "cd":
            return "CARTAO DEBITO"
        if "cc" in partes or palavra.endswith(" cc") or palavra == "cc":
            return "CARTAO CREDITO"
        if palavra in ("debito", "cd", "cartao debito", "cartao de debito"):
            # #region agent log
            _debug_nfse_log("extrair_forma_pagamento:return", "matched regex forma de pagamento -> debito", {"palavra": palavra, "valor": "CARTAO DEBITO"}, "A")
            # #endregion
            return "CARTAO DEBITO"
        if palavra in ("credito", "cc", "cartao credito", "cartao de credito"):
            # #region agent log
            _debug_nfse_log("extrair_forma_pagamento:return", "matched regex forma de pagamento -> credito", {"palavra": palavra, "valor": "CARTAO CREDITO"}, "A")
            # #endregion
            return "CARTAO CREDITO"
        if palavra in ("pix", "dinheiro", "dh", "especie", "boleto", "transferencia", "ted", "doc"):
            mapa = {"pix": "PIX", "dinheiro": "DINHEIRO", "dh": "DINHEIRO", "especie": "DINHEIRO", "boleto": "BOLETO", "transferencia": "TRANSFERENCIA", "ted": "TED", "doc": "DOC"}
            return mapa.get(palavra, palavra.upper())

    # Prioridade: frase explícita "forma de pagamento: X" ou "forma de pagamento (X)" para não confundir débito com crédito
    if "forma de pagamento: debito" in texto or "forma de pagamento: cd" in texto or "forma de pagamento (cd)" in texto or "forma de pagamento p(cd)" in texto or "forma de pagamento cd" in texto:
        # #region agent log
        _debug_nfse_log("extrair_forma_pagamento:return", "matched forma de pagamento debito/cd", {"valor": "CARTAO DEBITO"}, "A")
        # #endregion
        return "CARTAO DEBITO"
    if "forma de pagamento: credito" in texto or "forma de pagamento: cc" in texto or "forma de pagamento (cc)" in texto or "forma de pagamento p(cc)" in texto or "forma de pagamento cc" in texto:
        # #region agent log
        _debug_nfse_log("extrair_forma_pagamento:return", "matched forma de pagamento credito/cc", {"valor": "CARTAO CREDITO"}, "A")
        # #endregion
        return "CARTAO CREDITO"
    if "forma de pagamento: pix" in texto:
        return "PIX"
    if "forma de pagamento: dinheiro" in texto or "forma de pagamento: dh" in texto or "forma de pagamento: especie" in texto:
        return "DINHEIRO"
    if "forma de pagamento: boleto" in texto:
        return "BOLETO"
    if "forma de pagamento: transferencia" in texto:
        return "TRANSFERENCIA"
    if "forma de pagamento: ted" in texto:
        return "TED"
    if "forma de pagamento: doc" in texto:
        return "DOC"

    mapeamentos = {
        "cartao debito": "CARTAO DEBITO", "cartao de debito": "CARTAO DEBITO",
        "pgt: debito": "CARTAO DEBITO", "forma de pagamento: cartao de debito": "CARTAO DEBITO",
        "pagamento: cd": "CARTAO DEBITO", "pagamento: cc": "CARTAO CREDITO",
        "forma de pagamento (cd)": "CARTAO DEBITO", "forma de pagamento p(cd)": "CARTAO DEBITO", "forma de pagamento cd": "CARTAO DEBITO",
        "forma de pagamento (cc)": "CARTAO CREDITO", "forma de pagamento p(cc)": "CARTAO CREDITO", "forma de pagamento cc": "CARTAO CREDITO",
        "pagamento via cd": "CARTAO DEBITO", "pagamento via cartao de debito": "CARTAO DEBITO",
        "cartao credito": "CARTAO CREDITO", "cartao de credito": "CARTAO CREDITO",
        "pagamento via cc": "CARTAO CREDITO", "pgt: credito": "CARTAO CREDITO",
        # "dn" removido: substring em nomes (ex.: "Sidney") gerava DINHEIRO indevido
        "dh": "DINHEIRO", "especie": "DINHEIRO",
        "forma de pagamento: dinheiro": "DINHEIRO", "forma de pagamento: especie": "DINHEIRO",
        "forma de pagamento: pix": "PIX", "pagamento via pix": "PIX",
        "forma de pagamento: boleto": "BOLETO",
        "forma de pagamento: transferencia": "TRANSFERENCIA", "forma de pagamento: ted": "TED",
        "forma de pagamento: doc": "DOC",
    }
    for chave, valor in mapeamentos.items():
        if chave in texto:
            # #region agent log
            _debug_nfse_log("extrair_forma_pagamento:return", "matched mapeamentos", {"chave": chave, "valor": valor}, "A")
            # #endregion
            return valor
    _FORMA_CANONICA_PADROES = {"debito": "CARTAO DEBITO", "cd": "CARTAO DEBITO", "credito": "CARTAO CREDITO", "cc": "CARTAO CREDITO"}
    for p in PAGAMENTOS_PADROES:
        if p in texto:
            valor = _FORMA_CANONICA_PADROES.get(p, p.upper())
            # #region agent log
            _debug_nfse_log("extrair_forma_pagamento:return", "matched PAGAMENTOS_PADROES", {"padrao": p, "valor": valor}, "A")
            # #endregion
            return valor

    # Fallback regex para padrões do Portal Nacional
    fallback = re.search(
        r"forma\s+de\s+pagamento\s*:\s*(?:\d{1,3}(?:\.\d{3})*,\d{2}\s+|\d+,\d{2}\s+)?(PIX|CC|CD|DH|DINHEIRO|ESP[EÉ]CIE)\b",
        texto,
        re.IGNORECASE,
    )
    if fallback:
        sigla = fallback.group(1).upper().replace("É", "E")
        mapa = {"PIX": "PIX", "CC": "CARTAO CREDITO", "CD": "CARTAO DEBITO", "DH": "DINHEIRO", "DINHEIRO": "DINHEIRO", "ESPECIE": "DINHEIRO"}
        res = mapa.get(sigla, sigla)
        # #region agent log
        _debug_nfse_log("extrair_forma_pagamento:return", "matched fallback regex", {"sigla": sigla, "valor": res}, "A")
        # #endregion
        return res
    if re.search(r"\bno\s+cc\b", texto, re.IGNORECASE):
        return "CARTAO CREDITO"
    if re.search(r"\bno\s+cd\b", texto, re.IGNORECASE):
        return "CARTAO DEBITO"

    # #region agent log
    _debug_nfse_log("extrair_forma_pagamento:return", "no match", {"result": None}, "A")
    # #endregion
    return None


# Chaves (lowercase) que mapeiam para forma normalizada (para extrair_todas_formas)
_MAPEAMENTOS_FORMAS = [
    ("cartao débito", "CARTAO DEBITO"), ("cartão débito", "CARTAO DEBITO"),
    ("cartao de débito", "CARTAO DEBITO"), ("cartão de débito", "CARTAO DEBITO"),
    ("cartao de debito", "CARTAO DEBITO"), ("cartão debito", "CARTAO DEBITO"),
    ("pgt: debito", "CARTAO DEBITO"), ("forma de pagamento: cd", "CARTAO DEBITO"),
    ("pagamento via cd", "CARTAO DEBITO"), ("no cd", "CARTAO DEBITO"),
    ("cartao crédito", "CARTAO CREDITO"), ("cartão crédito", "CARTAO CREDITO"),
    ("cartao de crédito", "CARTAO CREDITO"), ("cartão de crédito", "CARTAO CREDITO"),
    ("forma de pagamento: cc", "CARTAO CREDITO"), ("pagamento via cc", "CARTAO CREDITO"),
    ("pgt: credito", "CARTAO CREDITO"), ("no cc", "CARTAO CREDITO"),
    ("dh", "DINHEIRO"), ("especie", "DINHEIRO"), ("espécie", "DINHEIRO"),
    ("forma de pagamento: dinheiro", "DINHEIRO"), ("forma de pagamento: espécie", "DINHEIRO"),
    ("forma de pagamento: dh", "DINHEIRO"), ("forma de pagamento: especie", "DINHEIRO"),
    ("forma de pagamento: pix", "PIX"), ("pagamento via pix", "PIX"),
    ("forma de pagamento: boleto", "BOLETO"),
    ("forma de pagamento: transferência", "TRANSFERENCIA"), ("forma de pagamento: ted", "TED"),
    ("forma de pagamento: doc", "DOC"),
]


# Códigos curtos -> forma canônica (evita duplicar CC e CARTAO CREDITO em extrair_todas_formas)
_FORMA_CANONICA = {"CC": "CARTAO CREDITO", "CD": "CARTAO DEBITO", "DH": "DINHEIRO", "DN": "DINHEIRO"}


def extrair_todas_formas_na_discriminacao(discriminacao: str) -> List[str]:
    """Retorna todas as formas de pagamento mencionadas na discriminação (sem duplicata)."""
    if not discriminacao:
        return []
    texto = discriminacao.lower()
    formas = []
    seen = set()
    for chave, valor in _MAPEAMENTOS_FORMAS:
        if chave in texto and valor not in seen:
            formas.append(valor)
            seen.add(valor)
    for p in PAGAMENTOS_PADROES:
        v = (p.upper() if len(p) > 2 else p.upper())
        v_canon = _FORMA_CANONICA.get(v, v)  # CC -> CARTAO CREDITO, CD -> CARTAO DEBITO, etc.
        if p in texto and v_canon not in seen:
            formas.append(v_canon)
            seen.add(v_canon)
    return formas


def _normalizar_valor_monetario_str(s: str) -> Optional[Decimal]:
    """
    Converte string de valor monetário para Decimal.
    Aceita formato brasileiro (23.700,00 ou R$ 5.100,00) e formato simples (100,00 ou 100.00).
    """
    if not s or not s.strip():
        return None
    s = s.strip()
    # Formato BR: vírgula como decimal (ex.: 23.700,00 ou 100,00)
    if "," in s and re.search(r",\d{2}$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


# Padrão que captura tanto BR (23.700,00) quanto simples (100,00 ou 100.00)
_PADRAO_VALOR_MONETARIO = re.compile(
    r"(?:R\$\s*)?((?:\d{1,3}(?:\.\d{3})*,\d{2})|(?:\d+[.,]\d{2}))",
    re.IGNORECASE,
)


def _extrair_valor_monetario_proximo(texto: str, forma_palavras: List[str]) -> Optional[Decimal]:
    """Procura valor monetário (R$ 100,00 ou 100,00 ou R$23.700,00) próximo a uma das palavras da forma."""
    for match in _PADRAO_VALOR_MONETARIO.finditer(texto):
        valor = _normalizar_valor_monetario_str(match.group(1))
        if valor is None or valor <= 0:
            continue
        inicio = max(0, match.start() - 50)
        fim = min(len(texto), match.end() + 50)
        janela = texto[inicio:fim].lower()
        if any(p in janela for p in forma_palavras):
            return valor
    return None


def extrair_valores_por_forma_da_discriminacao(
    discriminacao: str, formas: List[str]
) -> List[Tuple[str, Decimal]]:
    """
    Tenta extrair um valor associado a cada forma no texto.
    Retorna lista de (forma_normalizada, valor). Cada ocorrência monetária (posição) é usada no máximo uma vez.
    """
    if not discriminacao or not formas:
        return []
    texto = (discriminacao or "").strip().lower()
    resultado = []
    formas_ja_atribuidas = set()
    posicoes_utilizadas = set()
    forma_palavras = {
        "PIX": ["pix"],
        "CARTAO DEBITO": ["cartao debito", "cartão débito", "cd", "debito", "débito"],
        "CARTAO CREDITO": ["cartao credito", "cartão crédito", "cc", "credito", "crédito"],
        "DINHEIRO": ["dinheiro", "especie", "espécie", "dh"],
        "BOLETO": ["boleto"],
        "TRANSFERENCIA": ["transferencia", "transferência"],
        "TED": ["ted"],
        "DOC": ["doc"],
    }
    for m in _PADRAO_VALOR_MONETARIO.finditer(discriminacao or ""):
        start = m.start()
        if start in posicoes_utilizadas:
            continue
        v = _normalizar_valor_monetario_str(m.group(1))
        if v is None or v <= 0:
            continue
        inicio, fim = max(0, m.start() - 30), min(len(texto), m.end() + 30)
        janela = texto[inicio:fim]
        formas_na_janela = [
            f for f in formas
            if f not in formas_ja_atribuidas
            and any(p in janela for p in forma_palavras.get(f, [f.lower()]))
        ]
        if len(formas_na_janela) == 1:
            forma = formas_na_janela[0]
            resultado.append((forma, v))
            formas_ja_atribuidas.add(forma)
            posicoes_utilizadas.add(start)
    return resultado


def extrair_valores_mesma_forma_da_discriminacao(
    discriminacao: str, forma_normalizada: str
) -> List[Decimal]:
    """
    Extrai todos os valores monetários associados a uma única forma na discriminação,
    em ordem de aparição, sem repetir a mesma posição no texto.
    Usado para segmentação "mesma forma, vários valores" (ex.: dois CC com dois valores).
    """
    if not discriminacao or not forma_normalizada:
        return []
    forma_palavras = {
        "PIX": ["pix"],
        "CARTAO DEBITO": ["cartao debito", "cartão débito", "cd", "debito", "débito"],
        "CARTAO CREDITO": ["cartao credito", "cartão crédito", "cc", "credito", "crédito"],
        "DINHEIRO": ["dinheiro", "especie", "espécie", "dh"],
        "BOLETO": ["boleto"],
        "TRANSFERENCIA": ["transferencia", "transferência"],
        "TED": ["ted"],
        "DOC": ["doc"],
    }
    palavras = forma_palavras.get(
        (forma_normalizada or "").strip().upper(),
        [forma_normalizada.strip().lower()],
    )
    texto = (discriminacao or "").strip().lower()
    resultado: List[Decimal] = []
    posicoes_utilizadas: set = set()
    for m in _PADRAO_VALOR_MONETARIO.finditer(discriminacao or ""):
        start = m.start()
        if start in posicoes_utilizadas:
            continue
        v = _normalizar_valor_monetario_str(m.group(1))
        if v is None or v <= 0:
            continue
        inicio = max(0, m.start() - 50)
        fim = min(len(texto), m.end() + 50)
        janela = texto[inicio:fim]
        if any(p in janela for p in palavras):
            resultado.append(v)
            posicoes_utilizadas.add(start)
    return resultado


def extrair_aut_todos(discriminacao: str) -> List[str]:
    """Retorna todos os códigos AUT / STONE ID encontrados na discriminação."""
    if not discriminacao:
        return []
    padroes = [
        r"\bAUT[:\s]*([A-Za-z0-9\-/\.]+)",
        r"\bAUT([A-Za-z0-9\-/\.]+)",
        r"\bSTONE\s*ID[:\s]*([0-9]+)",
        r"\bSTONEID[:\s]*([0-9]+)",
        r"\bSTONED[:\s]*([0-9]+)",  # typo comum: STONED em vez de STONE
        r"\bSTONE\s*:\s*([0-9]+)",  # STONE: 12345 (não confunde com STONECODE)
        r"autorizacao[:\s]*([A-Za-z0-9\-/\.]+)",
    ]
    auts = []
    for pat in padroes:
        for m in re.finditer(pat, discriminacao, re.IGNORECASE):
            cod = (m.group(1) or "").strip()
            if cod and cod not in auts:
                auts.append(cod)
    return auts


def extrair_autorizacao(discriminacao: str) -> Optional[str]:
    """Primeiro código de autorização (AUT, STONE ID, etc.) na discriminação."""
    auts = extrair_aut_todos(discriminacao)
    return auts[0] if auts else None


def _eh_forma_cartao(forma_normalizada: str) -> bool:
    """True se a forma for cartão (crédito ou débito)."""
    if not forma_normalizada:
        return False
    f = (forma_normalizada or "").upper()
    return f in ("CARTAO CREDITO", "CARTAO DEBITO", "CC", "CD")


# Valor mínimo por segmento para permitir segmentação (evita segmentos irreais)
VALOR_MINIMO_SEGMENTO = Decimal("0.01")

# Palavras-chave de formas de pagamento (texto normalizado, sem acento) para padrão genérico
_FORMAS_PAGAMENTO_KEYWORDS = (
    r"pix|dh|dinheiro|especie|cc|cd|credito|debito|boleto|bol|ted|doc|transferencia|cartao"
)

def _indica_multi_pagamento(discriminacao: str) -> bool:
    """True se o texto sugerir duas ou mais formas de pagamento (qualquer combinação)."""
    if not discriminacao:
        return False
    t = _normalizar_texto(discriminacao)  # lower + sem acentos
    # Padrão genérico: forma1 (e|+|/) forma2 para qualquer par de formas
    generico = re.compile(
        r"(" + _FORMAS_PAGAMENTO_KEYWORDS + r")\s*(?:e|\+|/)\s*(" + _FORMAS_PAGAMENTO_KEYWORDS + r")",
        re.IGNORECASE,
    )
    m = generico.search(t)
    if m and m.group(1) != m.group(2):
        return True
    # Fallback: padrões explícitos "parte X parte Y"
    parte_padroes = [
        r"parte\s+pix\s+parte\s+cart", r"parte\s+cartao\s+parte\s+pix",
    ]
    for pat in parte_padroes:
        if re.search(pat, t):
            return True
    return False


# Forma normalizada -> (tpags aceitos, aliases de descrição) para match com Cobranca
# tpags: NF-e usa 03=Crédito, 04=Débito, 17=PIX, 01=Dinheiro; outros cadastros usam CC, CD, PIX
_FORMA_TPAG_ALIASES = {
    "CARTAO CREDITO": (["CC", "03", "3"], ["cc", "credito", "crédito", "cartao credito", "cartão crédito", "cartao de credito"]),
    "CARTAO DEBITO": (["CD", "04", "4"], ["cd", "debito", "débito", "cartao debito", "cartão débito", "cartao de debito"]),
    "PIX": (["PIX", "17"], ["pix"]),
    "DINHEIRO": (["DH", "01", "1"], ["dh", "dinheiro", "especie", "espécie"]),
    "BOLETO": (["BOL", "15"], ["boleto"]),
    "TRANSFERENCIA": (["TB", "04"], ["transferencia", "transferência"]),
    "TED": (["TED"], ["ted"]),
    "DOC": (["DOC"], ["doc"]),
}


def _encontra_cobranca_flexivel(forma_normalizada: str, cobrancas: List) -> Optional[object]:
    """Match flexível por descricao e tpag (case-insensitive, tolerante a acentos)."""
    # #region agent log
    _debug_nfse_log("_encontra_cobranca_flexivel:entry", "lookup Cobranca", {"forma_normalizada": forma_normalizada, "cobrancas_count": len(cobrancas or []), "sample": [(getattr(c, "tpag", None), getattr(c, "descricao", None)) for c in (cobrancas or [])[:5]]}, "B")
    # #endregion
    if not forma_normalizada:
        return None
    if not cobrancas:
        logger.warning(
            "Forma de pagamento: nenhuma Cobranca cadastrada. Cadastre em Cobrança (ex.: CC, PIX) para vincular."
        )
        return None
    alvo = _normalizar_texto(forma_normalizada)
    # Rótulo idêntico à forma (ex.: descrição "PIX") antes de substring genérico
    for cb in cobrancas:
        rotulo_eq = _normalizar_texto(
            (getattr(cb, "descricao", None) or getattr(cb, "nome", None) or "")
        )
        if rotulo_eq and rotulo_eq == alvo:
            return cb
    tpags_aceitos = set()
    aliases = set()
    fn = (forma_normalizada or "").strip().upper()
    if fn in _FORMA_TPAG_ALIASES:
        tpag_list, alias_list = _FORMA_TPAG_ALIASES[fn]
        tpags_aceitos = {str(t).strip().upper() for t in tpag_list}
        aliases = {_normalizar_texto(a) for a in alias_list}
    aliases.add(alvo)

    # Para cartão, não aceitar Cobrança cujo rótulo indique o tipo oposto (evita "cartao" casar com CARTAO CREDITO quando buscamos CARTAO DEBITO)
    def _rotulo_compativel(rotulo: str) -> bool:
        if fn != "CARTAO DEBITO" and fn != "CARTAO CREDITO":
            return True
        r = (rotulo or "").strip().lower()
        if fn == "CARTAO DEBITO" and "credito" in r:
            return False
        if fn == "CARTAO CREDITO" and "debito" in r:
            return False
        return True

    for cb in cobrancas:
        rotulo = _normalizar_texto(
            (getattr(cb, "descricao", None) or getattr(cb, "nome", None) or "")
        )
        tpag_cb = (getattr(cb, "tpag", None) or "").strip().upper()
        if tpags_aceitos and tpag_cb in tpags_aceitos:
            # #region agent log
            _debug_nfse_log("_encontra_cobranca_flexivel:return", "found by tpag", {"forma": forma_normalizada, "cob_id": getattr(cb, "pk", None), "cob_tpag": tpag_cb, "cob_descricao": getattr(cb, "descricao", None)}, "B")
            # #endregion
            return cb
        if rotulo in aliases and _rotulo_compativel(rotulo):
            # #region agent log
            _debug_nfse_log("_encontra_cobranca_flexivel:return", "found by rotulo", {"forma": forma_normalizada, "cob_id": getattr(cb, "pk", None), "cob_descricao": getattr(cb, "descricao", None)}, "B")
            # #endregion
            return cb
        if not rotulo:
            continue
        if (alvo in rotulo or rotulo in alvo) and _rotulo_compativel(rotulo):
            # #region agent log
            _debug_nfse_log("_encontra_cobranca_flexivel:return", "found by alvo/rotulo", {"forma": forma_normalizada, "cob_id": getattr(cb, "pk", None)}, "B")
            # #endregion
            return cb
        if any(w in rotulo for w in alvo.split() if len(w) >= 2) and _rotulo_compativel(rotulo):
            return cb
        if any(w in alvo for w in rotulo.split() if len(w) >= 2) and _rotulo_compativel(rotulo):
            # #region agent log
            _debug_nfse_log("_encontra_cobranca_flexivel:return", "found Cobranca", {"forma": forma_normalizada, "cob_id": getattr(cb, "pk", None), "cob_tpag": getattr(cb, "tpag", None), "cob_descricao": getattr(cb, "descricao", None)}, "B")
            # #endregion
            return cb
    # Diagnóstico: forma identificada mas nenhuma Cobranca correspondeu
    # #region agent log
    _debug_nfse_log("_encontra_cobranca_flexivel:return", "no Cobranca found", {"forma_normalizada": forma_normalizada}, "B")
    # #endregion
    amostra = [
        (getattr(cb, "tpag", None), getattr(cb, "descricao", None) or getattr(cb, "nome", None))
        for cb in cobrancas[:5]
    ]
    logger.info(
        "Forma de pagamento: forma '%s' não encontrou Cobranca. Cadastros (tpag, descricao): %s",
        forma_normalizada,
        amostra,
    )
    return None


def detectar_forma_pagamento_e_vincular(
    discriminacao: str,
    cobrancas: List,
    valor_total_nfse: Optional[Decimal] = None,
    valor_liquido_nfse: Optional[Decimal] = None,
) -> Tuple[Optional[object], str, Optional[List[Tuple[Decimal, object]]]]:
    """
    Extrai forma de pagamento da discriminação e encontra Cobranca correspondente.
    Retorna (Cobranca, motivo, segmentos) ou (None, motivo, segmentos).
    segmentos: quando multi-form com 2+ valores que somam valor_total_nfse (ou valor_liquido_nfse), lista de (valor_bruto, Cobranca).
    Motivos: 'vinculado' | 'nao_identificado' | 'multi_pagamento_detectado' | 'multi_pagamento_sem_valores' | 'multi_segmentar' | 'sem_match_no_cadastro'

    Segmentação só ocorre quando há valores explícitos no texto para cada forma; se o cliente
    informar apenas "pago no pix e dh" (ou outra combinação) sem valores, o motivo será
    multi_pagamento_sem_valores e não haverá segmentação.
    Para "mesma forma, vários valores", a soma extraída pode bater com valor_total_nfse (bruto) ou valor_liquido_nfse (líquido), dentro da tolerância.
    """
    if not discriminacao or not discriminacao.strip():
        return (None, "nao_identificado", None)
    if _indica_multi_pagamento(discriminacao):
        formas = extrair_todas_formas_na_discriminacao(discriminacao)
        if len(formas) < 2:
            logger.info(
                "Forma de pagamento: multi_pagamento_detectado (menos de 2 formas) | formas=%s | discriminacao=%s",
                formas, (discriminacao or "")[:200],
            )
            return (None, "multi_pagamento_detectado", None)
        pares = extrair_valores_por_forma_da_discriminacao(discriminacao, formas)
        if not pares or len(pares) < 2:
            logger.info(
                "Forma de pagamento: multi_pagamento_sem_valores (menos de 2 pares) | formas=%s | pares=%s | discriminacao=%s",
                len(formas), len(pares), (discriminacao or "")[:200],
            )
            return (None, "multi_pagamento_sem_valores", None)
        for _forma, valor in pares:
            if valor < VALOR_MINIMO_SEGMENTO:
                logger.info(
                    "Forma de pagamento: multi_pagamento_sem_valores (valor abaixo do minimo) | valor=%.2f | discriminacao=%s",
                    float(valor), (discriminacao or "")[:200],
                )
                return (None, "multi_pagamento_sem_valores", None)
        total = sum(v for (_, v) in pares)
        if valor_total_nfse is None or abs(total - valor_total_nfse) > Decimal("0.05"):
            logger.info(
                "Forma de pagamento: multi_pagamento_sem_valores (soma diferente do total) | soma=%.2f | total_nfse=%s | discriminacao=%s",
                float(total), valor_total_nfse, (discriminacao or "")[:200],
            )
            return (None, "multi_pagamento_sem_valores", None)
        pares_ordenados = sorted(pares, key=lambda x: (x[0], str(x[1])))
        segmentos = []
        for forma, valor in pares_ordenados:
            cob = _encontra_cobranca_flexivel(forma, cobrancas)
            if not cob:
                logger.info(
                    "Forma de pagamento: multi_pagamento_sem_valores (sem Cobranca para forma %s) | discriminacao=%s",
                    forma, (discriminacao or "")[:200],
                )
                return (None, "multi_pagamento_sem_valores", None)
            segmentos.append((valor, cob))
        logger.info(
            "Forma de pagamento: multi_segmentar | pares=%s | soma=%.2f | total_nfse=%s",
            [(f, float(v)) for f, v in pares_ordenados], float(total), valor_total_nfse,
        )
        return (None, "multi_segmentar", segmentos)
    forma = extrair_forma_pagamento(discriminacao)
    if forma:
        valores = extrair_valores_mesma_forma_da_discriminacao(discriminacao, forma)
        if len(valores) >= 2:
            if any(v < VALOR_MINIMO_SEGMENTO for v in valores):
                logger.info(
                    "Forma de pagamento: mesma forma varios valores (valor abaixo do minimo) | forma=%s | valores=%s | discriminacao=%s",
                    forma, [float(v) for v in valores], (discriminacao or "")[:200],
                )
            else:
                total = sum(valores)
                tolerancia = Decimal("0.05")
                soma_bate_bruto = valor_total_nfse is not None and abs(total - valor_total_nfse) <= tolerancia
                soma_bate_liquido = valor_liquido_nfse is not None and abs(total - valor_liquido_nfse) <= tolerancia
                if soma_bate_bruto or soma_bate_liquido:
                    cob = _encontra_cobranca_flexivel(forma, cobrancas)
                    if cob:
                        auts = extrair_aut_todos(discriminacao)
                        if len(auts) >= len(valores) and _eh_forma_cartao(forma):
                            segmentos = [(v, cob, auts[i]) for i, v in enumerate(valores)]
                        else:
                            segmentos = [(v, cob, None) for v in valores]
                        ref = valor_total_nfse if soma_bate_bruto else valor_liquido_nfse
                        logger.info(
                            "Forma de pagamento: multi_segmentar (mesma forma, varios valores) | forma=%s | valores=%s | soma=%.2f | ref=%.2f",
                            forma, [float(v) for v in valores], float(total), float(ref),
                        )
                        return (None, "multi_segmentar", segmentos)
                else:
                    logger.info(
                        "Forma de pagamento: mesma forma varios valores (soma diferente do total) | forma=%s | soma=%.2f | bruto=%s | liquido=%s | discriminacao=%s",
                        forma, float(total), valor_total_nfse, valor_liquido_nfse, (discriminacao or "")[:200],
                    )
    if not forma:
        logger.debug("Forma de pagamento: nao_identificado")
        return (None, "nao_identificado", None)
    cob = _encontra_cobranca_flexivel(forma, cobrancas)
    if not cob:
        logger.debug("Forma de pagamento: sem_match_no_cadastro (forma=%s)", forma)
        return (None, "sem_match_no_cadastro", None)
    return (cob, "vinculado", None)


def _extrair_numero_dps_sped(infnfse_elem) -> str:
    """
    Número da DPS usado na consulta GET /dps/{id42} na SEFIN.
    Preferência: tag ``nDPS``; senão, últimos 15 dígitos numéricos do atributo ``Id`` de ``infDPS`` (após ``DPS``).
    """
    v = _t(infnfse_elem, "DPS/infDPS/nDPS", NS_SPED)
    if v:
        return v.strip()
    inf = _find_ns(infnfse_elem, "DPS/infDPS", NS_SPED)
    if inf is None:
        return ""
    raw = (inf.get("Id") or "").strip()
    if not raw:
        return ""
    body = raw[3:] if raw.upper().startswith("DPS") else raw
    digits = re.sub(r"\D", "", body)
    if len(digits) < 15:
        return ""
    tail = digits[-15:]
    try:
        return str(int(tail))
    except ValueError:
        return tail.lstrip("0") or "0"


def import_nfse_sped(
    infnfse_elem,
    user,
    empresa,
    cobrancas: Optional[List] = None,
    importar_canceladas: bool = False,
):
    """
    Importa uma NFSe no formato SPED (Portal Nacional).
    infnfse_elem: elemento infNFSe (com namespace).
    cobrancas: lista de Cobranca para match de forma_pagamento (evita N+1).
    Retorna NotaFiscalServico preenchida (não salva no banco).
    """
    if cobrancas is None:
        from cobranca.models import Cobranca
        cobrancas = list(Cobranca.objects.all())

    # #region agent log
    _debug_nfse_log("import_nfse_sped:cobrancas", "cobrancas list", {"count": len(cobrancas), "items": [(getattr(c, "tpag", None), getattr(c, "descricao", None)) for c in cobrancas[:10]]}, "C")
    # #endregion

    numero_nota = _t(infnfse_elem, "nNFSe", NS_SPED)
    if not numero_nota:
        raise ValueError("Número da NFSe (nNFSe) não encontrado no XML SPED")

    serie = _t(infnfse_elem, "DPS/infDPS/serie", NS_SPED) or "1"
    numero_dps_raw = _extrair_numero_dps_sped(infnfse_elem)
    numero_dps_val = (numero_dps_raw or "").strip()[:20] or None
    data_emissao = (
        _d(infnfse_elem, "dhProc", NS_SPED)
        or _d(infnfse_elem, "dhEmi", NS_SPED)
        or _d(infnfse_elem, "DPS/infDPS/dhEmi", NS_SPED)
    )
    if not data_emissao:
        data_emissao = date.today()

    cliente = (
        _t_primeiro(infnfse_elem, [
            "DPS/infDPS/toma/xNome",
            "toma/xNome",
        ])
        or "Cliente não identificado"
    )
    cnpj_cpf = (
        _t_primeiro(infnfse_elem, [
            "DPS/infDPS/toma/CNPJ",
            "DPS/infDPS/toma/CPF",
            "toma/CNPJ",
            "toma/CPF",
        ])
        or ""
    )
    discriminacao = _t_primeiro(infnfse_elem, [
        "serv/cServ/xDescServ",
        "DPS/infDPS/serv/cServ/xDescServ",
        "DPS/infDPS/serv/xDescServ",
    ])
    _nfs_import_debug_log(
        "info",
        "[NFS_IMPORT_DEBUG] SPED discriminacao extraída: len=%s, primeiros_200=%s",
        len(discriminacao or ""),
        (discriminacao or "")[:200],
    )

    # Valores principais: valor bruto da tag vBC, valor líquido da tag vLiq
    valor_bruto = _dec_primeiro(infnfse_elem, [
        "valores/vBC",
        "valores/vServPrest/vServ",
        "DPS/infDPS/valores/vServPrest/vServ",
        "DPS/infDPS/valores/vServ",
    ])
    valor_liq = _dec_primeiro(infnfse_elem, [
        "valores/vLiq",
        "DPS/infDPS/valores/vLiq",
    ])
    valor_liquido = valor_liq if valor_liq > 0 else valor_bruto
    if not valor_bruto or valor_bruto <= 0:
        valor_bruto = valor_liquido

    ibscbs = _extrair_ibscbs_sped(infnfse_elem)
    v_total_ret = _dec(infnfse_elem, "valores/vTotalRet", NS_SPED)
    v_iss_xml = _dec(infnfse_elem, "valores/vISSQN", NS_SPED)

    v_pis = _dec(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribFed/piscofins/vPis",
        NS_SPED,
    )
    v_cofins = _dec(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribFed/piscofins/vCofins",
        NS_SPED,
    )
    v_ret_irrf = _dec(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribFed/vRetIRRF",
        NS_SPED,
    )
    v_ret_csll = _dec(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribFed/vRetCSLL",
        NS_SPED,
    )

    # Se tpRetPisCofins 0 ou 2 (operação sem retenção), zerar PIS, COFINS, CSLL e IRPJ
    tp_ret_pis_cofins = _t(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribFed/piscofins/tpRetPisCofins",
        NS_SPED,
    ) or _t(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribFed/tpRetPisCofins",
        NS_SPED,
    )
    if tp_ret_pis_cofins in ("0", "2"):
        v_pis = Decimal("0")
        v_cofins = Decimal("0")
        v_ret_irrf = Decimal("0")
        v_ret_csll = Decimal("0")

    # ISS retido: conforme empresa.utiliza_iss_fixo e tags tpRetISSQN, vISSQN, pAliqAplic
    tp_ret = _t(
        infnfse_elem,
        "DPS/infDPS/valores/trib/tribMun/tpRetISSQN",
        NS_SPED,
    )

    from decimal import Decimal as _D

    utiliza_iss_fixo = getattr(empresa, "utiliza_iss_fixo", True)
    if not utiliza_iss_fixo and tp_ret == "2":
        iss_retido = True
        valor_iss_retido_xml = v_iss_xml if v_iss_xml > 0 else _D("0")
    else:
        iss_retido = False
        valor_iss_retido_xml = _D("0")

    # Outras retenções: tentar tag direta (vOutrasRet); senão = vTotalRet - (PIS + COFINS + IRRF + CSLL + ISS)
    outras_retencoes_xml = _dec(infnfse_elem, "valores/vOutrasRet", NS_SPED)
    if outras_retencoes_xml <= _D("0"):
        outras_retencoes_xml = _dec(infnfse_elem, "DPS/infDPS/valores/vOutrasRet", NS_SPED)
    if outras_retencoes_xml <= _D("0"):
        soma_ret_básicas = (
            v_pis + v_cofins + v_ret_irrf + v_ret_csll + valor_iss_retido_xml
        )
        if v_total_ret > 0:
            diff = v_total_ret - soma_ret_básicas
            if abs(diff) > _D("0.01"):
                outras_retencoes_xml = max(_D("0"), diff)

    # Alíquota ISS (pAliqAplic) — usada quando utiliza_iss_fixo=N e tpRetISSQN=2; se ISS retido=N, alíquota=0
    aliquota_iss_xml = _dec(infnfse_elem, "valores/pAliqAplic", NS_SPED) if iss_retido else _D("0")

    # Se é importação de lote de notas canceladas, zerar valores e retenções,
    # mantendo apenas identificação e metadados
    if importar_canceladas:
        valor_bruto = _D("0")
        valor_liquido = _D("0")
        v_pis = _D("0")
        v_cofins = _D("0")
        v_ret_irrf = _D("0")
        v_ret_csll = _D("0")
        valor_iss_retido_xml = _D("0")
        outras_retencoes_xml = _D("0")
        aliquota_iss_xml = _D("0")
        ibscbs_kwargs = _kwargs_ibscbs_nfse(ibscbs, zerar=True)

    zero = Decimal("0")
    if not importar_canceladas:
        ibscbs_kwargs = _kwargs_ibscbs_nfse(ibscbs)
    cob, motivo, segmentos = detectar_forma_pagamento_e_vincular(
        discriminacao or "", cobrancas,
        valor_total_nfse=valor_bruto,
        valor_liquido_nfse=valor_liquido,
    )
    if motivo == "multi_segmentar" and segmentos and len(segmentos) >= 2:
        valor_total_seg = sum(seg[0] for seg in segmentos)
        nfses_segmentadas = []
        for i, seg in enumerate(segmentos, 1):
            valor_seg, cob_seg = seg[0], seg[1]
            nsu_seg = seg[2] if len(seg) >= 3 else None
            proporcao = valor_seg / valor_total_seg if valor_total_seg else Decimal("1")
            valor_liq_seg = valor_liquido * proporcao
            nfse_seg = NotaFiscalServico(
                empresa=empresa,
                numero_nota="%s-%s" % (numero_nota.strip(), i),
                serie=serie.strip(),
                numero_dps=numero_dps_val,
                data_emissao=data_emissao,
                cliente=cliente.strip(),
                cnpj_cpf=(cnpj_cpf or "").strip(),
                discriminacao=discriminacao.strip() or None,
                valor_bruto=valor_seg,
                valor_liquido=valor_liq_seg,
                valor_deducoes=zero,
                valor_pis=v_pis,
                valor_cofins=v_cofins,
                valor_inss=zero,
                valor_ir=v_ret_irrf,
                valor_csll=v_ret_csll,
                iss_retido=iss_retido,
                valor_iss_retido=valor_iss_retido_xml,
                outras_retencoes=outras_retencoes_xml,
                aliquota=aliquota_iss_xml,
                status_conciliacao='nao_conciliado',
                forma_pagamento=cob_seg,
                **_ibscbs_proporcional(ibscbs_kwargs, proporcao),
            )
            if nsu_seg is not None:
                nfse_seg.nsu = nsu_seg
            else:
                auts = extrair_aut_todos(discriminacao or "")
                if _eh_forma_cartao(getattr(cob_seg, "descricao", None) or ""):
                    if len(auts) == 1:
                        nfse_seg.nsu = auts[0]
                    elif len(auts) > 1:
                        logger.debug("NFSe %s-%s: multi_aut_detectado (não preenchendo nsu)", numero_nota, i)
            nfses_segmentadas.append(nfse_seg)
        logger.info("NFSe SPED segmentada: %s em %s notas", numero_nota, len(nfses_segmentadas))
        return nfses_segmentadas

    nfse = NotaFiscalServico(
        empresa=empresa,
        numero_nota=numero_nota.strip(),
        serie=serie.strip(),
        numero_dps=numero_dps_val,
        data_emissao=data_emissao,
        cliente=cliente.strip(),
        cnpj_cpf=(cnpj_cpf or "").strip(),
        discriminacao=discriminacao.strip() or None,
        valor_bruto=valor_bruto,
        valor_liquido=valor_liquido,
        valor_deducoes=zero,
        valor_pis=v_pis,
        valor_cofins=v_cofins,
        valor_inss=zero,
        valor_ir=v_ret_irrf,
        valor_csll=v_ret_csll,
        iss_retido=iss_retido,
        valor_iss_retido=valor_iss_retido_xml,
        outras_retencoes=outras_retencoes_xml,
        aliquota=aliquota_iss_xml,
        status_conciliacao="nao_conciliado",
        data_cancelamento=data_emissao if importar_canceladas else None,
        **ibscbs_kwargs,
    )
    nfse.forma_pagamento = cob if cob else None
    forma_unica = extrair_forma_pagamento(discriminacao or "") if discriminacao else None
    auts = extrair_aut_todos(discriminacao or "")
    if forma_unica and _eh_forma_cartao(forma_unica):
        if len(auts) == 1:
            nfse.nsu = auts[0]
        elif len(auts) > 1:
            logger.debug("NFSe %s: multi_aut_detectado (não preenchendo nsu)", numero_nota)
    else:
        nfse.nsu = None
    if not cob and motivo not in ("nao_identificado",):
        logger.debug("NFSe %s forma_pagamento não vinculado: %s", numero_nota, motivo)

    _nfs_import_debug_log(
        "info",
        "[NFS_IMPORT_DEBUG] SPED antes de retornar nfse: numero_nota=%s, discriminacao_len=%s, forma_pagamento_id=%s",
        numero_nota,
        len(nfse.discriminacao or ""),
        getattr(nfse.forma_pagamento, "pk", None),
    )
    logger.info("NFSe SPED importada: %s, cliente=%s", numero_nota, cliente[:50])
    return nfse


def import_lote_nfse_sped(root, user, empresa, importar_canceladas: bool = False):
    """
    Importa lote de NFSe no formato SPED (Portal Nacional).
    root: elemento raiz NFSe (com namespace).
    Retorna o mesmo formato de import_lote_nfse: nfses, notas_importadas, notas_ignoradas, totais.
    """
    from cobranca.models import Cobranca
    cobrancas = list(Cobranca.objects.all())

    ns = NS_SPED
    tag_inf = _qname(ns, "infNFSe")
    inf_list = root.findall(".//%s" % tag_inf)
    if not inf_list:
        inf_one = root.find(tag_inf)
        if inf_one is not None:
            inf_list = [inf_one]

    nfses = []
    notas_importadas = []
    notas_ignoradas = []
    processadas = 0

    for infnfse in inf_list:
        processadas += 1
        try:
            resultado = import_nfse_sped(
                infnfse,
                user,
                empresa,
                cobrancas=cobrancas,
                importar_canceladas=importar_canceladas,
            )
        except Exception as e:
            logger.warning("Erro ao importar infNFSe SPED: %s", e)
            notas_ignoradas.append({
                "numero_nota": "infNFSe #%s" % processadas,
                "cliente": "Erro na importação",
                "motivo": str(e),
            })
            continue

        nfses_retorno = resultado if isinstance(resultado, list) else [resultado]
        for nfse in nfses_retorno:
            nota_existente = NotaFiscalServico.objects.filter(
                empresa=empresa,
                numero_nota=nfse.numero_nota,
                serie=nfse.serie,
            ).first()
            if nota_existente:
                notas_ignoradas.append({
                    "numero_nota": nfse.numero_nota,
                    "cliente": nfse.cliente,
                    "motivo": "Nota já existe no banco",
                })
                continue
            duplicata_lote = any(
                n.numero_nota == nfse.numero_nota and n.serie == nfse.serie for n in nfses
            )
            if duplicata_lote:
                notas_ignoradas.append({
                    "numero_nota": nfse.numero_nota,
                    "cliente": nfse.cliente,
                    "motivo": "Duplicata no XML",
                })
                continue
            nfses.append(nfse)
            notas_importadas.append({
                "numero_nota": nfse.numero_nota,
                "cliente": nfse.cliente,
                "valor_liquido": float(nfse.valor_liquido),
            })

    return {
        "nfses": nfses,
        "notas_importadas": notas_importadas,
        "notas_ignoradas": notas_ignoradas,
        "total_processadas": processadas,
        "total_importadas": len(nfses),
        "total_ignoradas": len(notas_ignoradas),
    }


def limpar_cnpj(cnpj: str) -> str:
    """
    Limpa o CNPJ removendo formatação (pontos, barras, traços)
    """
    if not cnpj:
        return ""
    return ''.join(filter(str.isdigit, cnpj))

def find_numero_nota_correct(scope):
    """
    Busca especificamente pelo número da nota no local correto:
    - Deve estar dentro de InfNfse
    - Não deve estar dentro de Endereco, TomadorServico, PrestadorServico, etc.
    """
    safe_print("=== DEBUG find_numero_nota_correct ===")
    
    # Primeiro, vamos tentar uma busca mais específica por caminho
    # Buscar especificamente por InfNfse/Numero
    for elem in scope.iter():
        lname = _local(elem.tag)
        if lname == 'infnfse':
            # Dentro de InfNfse, buscar por Numero
            for child in elem.iter():
                child_lname = _local(child.tag)
                if child_lname == 'numero':
                    text = (child.text or '').strip()
                    if text:
                        safe_print(f"[OK] Número da nota encontrado no caminho correto: {text}")
                        return text
    
    # Se não encontrou pelo caminho específico, vamos usar uma abordagem mais inteligente
    # Buscar por elementos Numero e verificar o contexto
    numero_candidates = []
    
    for elem in scope.iter():
        lname = _local(elem.tag)
        text = (elem.text or '').strip()
        if not text:
            continue
            
        if lname == 'numero':
            # Verificar o contexto deste elemento
            context = get_element_context(elem, scope)
            print(f"Tag 'numero' encontrada com valor '{text}' no contexto: {context}")
            
            # Se está diretamente dentro de InfNfse, é o número da nota
            if context == 'infnfse':
                safe_print(f"[OK] Número da nota encontrado no contexto correto (InfNfse): {text}")
                return text
            elif context not in ['endereco', 'tomadorservico', 'prestadorservico', 'identificacaotomador']:
                # Se não está em um contexto problemático, pode ser o número da nota
                numero_candidates.append((text, context))
                safe_print(f"[AVISO] Possível número da nota: {text} (contexto: {context})")
    
    # Se encontrou candidatos, retornar o primeiro que não seja de endereço
    if numero_candidates:
        for numero, context in numero_candidates:
            if context not in ['endereco']:
                safe_print(f"[OK] Usando número da nota: {numero} (contexto: {context})")
                return numero
    
    safe_print("[ERRO] Número da nota não encontrado no local correto")
    return None

def get_element_context(elem, scope):
    """
    Determina o contexto de um elemento XML
    """
    try:
        # Tentar usar getparent() se disponível
        parent = elem.getparent()
        if parent is not None:
            return _local(parent.tag)
    except AttributeError:
        pass
    
    # Fallback: buscar o pai navegando pela árvore
    # Isso é mais lento mas funciona em todas as versões do ElementTree
    for parent_elem in scope.iter():
        for child in parent_elem:
            if child is elem:
                return _local(parent_elem.tag)
    
    return 'unknown'


_TAGS_VALOR_BRUTO_ABRASF = frozenset({
    'valorservicos', 'valorservico', 'basecalculo', 'vbc', 'valorbruto',
})
_TAGS_VALOR_LIQUIDO_ABRASF = frozenset({
    'valorliquidonfse', 'valorliquido', 'vliq',
})


def _parse_valor_xml(text) -> Decimal:
    """Converte texto de valor XML (1000.00 ou 300,00 ou 1.234,56) para Decimal."""
    if text is None:
        return Decimal('0')
    if isinstance(text, Decimal):
        return text
    s = str(text).strip()
    if not s:
        return Decimal('0')
    parsed = _normalizar_valor_monetario_str(s)
    if parsed is not None:
        return parsed
    try:
        return Decimal(s.replace(',', '.'))
    except Exception:
        return Decimal('0')


def _texto_elemento_xml(elem) -> str:
    """Texto do elemento ou atributo com valor monetário (alguns XMLs antigos)."""
    text = (elem.text or '').strip()
    if text:
        return text
    for attr in ('valor', 'Value', 'value'):
        av = elem.get(attr)
        if av and str(av).strip():
            return str(av).strip()
    return ''


def _extrair_valores_nfse_scope(scope) -> tuple[Decimal, Decimal]:
    """
    Extrai valor bruto e líquido de InfNfse ABRASF (Rio Branco modelo antigo/novo).
    Aceita vírgula decimal e tags BaseCalculo / ValorServicos / ValorLiquidoNfse.
    """
    bruto_vals: list[Decimal] = []
    liquido_vals: list[Decimal] = []
    for elem in scope.iter():
        lname = _local(elem.tag)
        raw = _texto_elemento_xml(elem)
        if not raw:
            continue
        val = _parse_valor_xml(raw)
        if val <= 0:
            continue
        if lname in _TAGS_VALOR_BRUTO_ABRASF:
            bruto_vals.append(val)
        if lname in _TAGS_VALOR_LIQUIDO_ABRASF:
            liquido_vals.append(val)
    bruto = max(bruto_vals) if bruto_vals else Decimal('0')
    liquido = max(liquido_vals) if liquido_vals else Decimal('0')
    if bruto <= 0 and liquido > 0:
        bruto = liquido
    elif liquido <= 0 and bruto > 0:
        liquido = bruto
    return bruto, liquido


def _compnfse_tem_cancelamento(comp_elem) -> bool:
    """True se o CompNfse ABRASF inclui bloco NfseCancelamento (nota cancelada na prefeitura)."""
    return any(_local(child.tag) == 'nfsecancelamento' for child in comp_elem)


def _iter_infnfse_lote_abrasf(root):
    """
    Itera pares (InfNfse, cancelada) de um lote ConsultarNfseLote / ListaNfse.
    Cancelamento é por CompNfse — não pelo arquivo inteiro (lotes misturam ativas e canceladas).
    """
    for comp in root.iter():
        if _local(comp.tag) != 'compnfse':
            continue
        cancelada = _compnfse_tem_cancelamento(comp)
        infnfse = None
        for child in comp:
            if _local(child.tag) != 'nfse':
                continue
            for sub in child.iter():
                if _local(sub.tag) == 'infnfse':
                    infnfse = sub
                    break
            if infnfse is not None:
                break
        if infnfse is not None:
            yield infnfse, cancelada


def _xml_ficheiro_vem_de_pasta_cancelada(nome: str) -> bool:
    """True se o caminho/nome lógico indica subpasta ``Cancelada/`` (importação inbox ou cópias)."""
    if not nome:
        return False
    n = nome.replace("\\", "/").strip().lower()
    return n.startswith("cancelada/") or "/cancelada/" in n


def import_nfse_from_xml(xml_file, user, empresa, importar_canceladas: bool = False):
    """
    Importa dados de NFSe a partir de um arquivo XML
    Suporta tanto NFSe individual quanto lote de NFSe
    Valida se o CNPJ da empresa prestadora de serviço é igual ao CNPJ da empresa selecionada
    """
    importar_canceladas = bool(importar_canceladas) or _xml_ficheiro_vem_de_pasta_cancelada(
        getattr(xml_file, "name", "") or ""
    )
    safe_print("=== DEBUG import_nfse_from_xml ===")
    safe_print(f"Arquivo: {xml_file.name}, Usuario: {user.username}, Empresa: {empresa.razao}")

    if _conteudo_xml_vazio(xml_file):
        nome = getattr(xml_file, "name", "") or "nota.xml"
        safe_print(f"[AVISO] Arquivo vazio ignorado: {nome}")
        return resultado_importacao_arquivo_vazio(nome)

    xml_bytes = b""
    try:
        if hasattr(xml_file, "seek") and hasattr(xml_file, "read"):
            xml_file.seek(0)
            xml_bytes = xml_file.read() or b""
            xml_file.seek(0)
    except Exception:
        xml_bytes = b""

    try:
        # Parse do XML com tratamento específico para erros de arquivo
        print("Fazendo parse do XML...")
        try:
            root = _parse_xml_root(xml_file)
            print(f"Root tag: {root.tag}")
            from notasfiscais.nfse_xml_copia import (
                abrasf_xml_indica_cancelada,
                tentar_salvar_copia_xml_importacao,
                xml_nfse_portal_indica_cancelada,
            )

            root_local = _local(root.tag)
            is_lote_abrasf = root_local in ("consultarnfselote", "listanfse", "lotenotafiscal")

            # Heurística de cancelamento: SPED (portal nacional) ou ABRASF explícito — nunca por palavra solta «nfse»
            # Lotes ABRASF (Rio Branco) podem conter NfseCancelamento só em alguns CompNfse — não marcar o arquivo inteiro.
            if _is_nfse_sped(root):
                importar_canceladas = bool(importar_canceladas) or xml_nfse_portal_indica_cancelada(xml_bytes)
            elif not is_lote_abrasf:
                importar_canceladas = bool(importar_canceladas) or abrasf_xml_indica_cancelada(xml_bytes)
        except OSError as os_err:
            # Trata especificamente erros de sistema de arquivos (como [Errno 22] Invalid argument)
            safe_print(f"[ERRO] Erro de sistema de arquivos ao abrir XML: {str(os_err)}")
            safe_print(f"[ERRO] Nome do arquivo: '{xml_file.name}'")
            safe_print(f"[ERRO] Tipo de erro: {type(os_err).__name__}")
            if hasattr(os_err, 'errno'):
                safe_print(f"[ERRO] Código do erro: {os_err.errno}")
            # Log adicional para debug
            logger.error(f"OSError ao abrir XML: arquivo='{xml_file.name}', erro='{str(os_err)}', errno={getattr(os_err, 'errno', 'N/A')}")
            raise ValueError(f"Erro ao acessar arquivo XML: {str(os_err)}. Verifique se o nome do arquivo contém caracteres especiais ou se o arquivo está corrompido.")
        except ET.ParseError as parse_err:
            safe_print(f"[ERRO] Erro de parsing XML: {str(parse_err)}")
            safe_print(f"[ERRO] Arquivo pode estar corrompido ou ter formato inválido")
            raise ValueError(f"Erro ao processar XML: {str(parse_err)}")
        except ValueError:
            raise

        from notasfiscais.nfse_evento_cancelamento import (
            import_evento_cancelamento_nfse,
            is_evento_cancelamento_nfse,
        )
        if is_evento_cancelamento_nfse(root):
            logger.info("XML detectado como evento de cancelamento NFS-e (SPED)")
            return import_evento_cancelamento_nfse(xml_file, user, empresa)
        
        # Portal Nacional (SPED NFSe): root NFSe com namespace http://www.sped.fazenda.gov.br/nfse
        if _is_nfse_sped(root):
            logger.info("XML detectado como SPED NFSe (Portal Nacional)")
            resultado = import_lote_nfse_sped(
                root,
                user,
                empresa,
                importar_canceladas=importar_canceladas,
            )
            for nfse in resultado["nfses"]:
                try:
                    if getattr(nfse, "empresa_id", None):
                        socio = extrair_socio(nfse.discriminacao or "", Socio.objects.filter(empresa_id=nfse.empresa_id))
                        if socio:
                            nfse.socio = socio
                    _nfs_import_debug_log(
                        "info",
                        "[NFS_IMPORT_DEBUG] Antes save() SPED: numero_nota=%s, discriminacao_len=%s, forma_pagamento_id=%s",
                        getattr(nfse, "numero_nota", None),
                        len(getattr(nfse, "discriminacao", None) or ""),
                        getattr(getattr(nfse, "forma_pagamento", None), "pk", None),
                    )
                    nfse.save()
                    _nfs_import_debug_log(
                        "info",
                        "[NFS_IMPORT_DEBUG] Após save() SPED: pk=%s, forma_pagamento_id=%s",
                        nfse.pk,
                        getattr(nfse.forma_pagamento, "pk", None),
                    )
                    logger.info("NFSe SPED salva: %s", nfse.numero_nota)
                except Exception as e:
                    logger.warning("Erro ao salvar NFSe SPED %s: %s", nfse.numero_nota, e)
                    resultado["notas_ignoradas"].append({
                        "numero_nota": nfse.numero_nota,
                        "cliente": nfse.cliente,
                        "motivo": "Erro ao salvar: %s" % str(e),
                    })
                    resultado["notas_importadas"] = [
                        n for n in resultado["notas_importadas"]
                        if n["numero_nota"] != nfse.numero_nota
                    ]
                    resultado["total_importadas"] -= 1
            tentar_salvar_copia_xml_importacao(
                xml_bytes,
                getattr(xml_file, "name", "nfse.xml") or "nfse.xml",
                empresa,
                root,
                importar_canceladas,
                resultado,
            )
            return resultado

        # Verifica se é um lote de NFSe ou NFSe individual (ABRASF)
        if _local(root.tag) in ("consultarnfselote", "listanfse", "lotenotafiscal"):
            print("Detectado: Lote de NFSe")
            resultado = import_lote_nfse(root, user, empresa, importar_canceladas=importar_canceladas)

            # Salvar todas as NFSe do lote
            for nfse in resultado['nfses']:
                try:
                    if getattr(nfse, "empresa_id", None):
                        socio = extrair_socio(nfse.discriminacao or "", Socio.objects.filter(empresa_id=nfse.empresa_id))
                        if socio:
                            nfse.socio = socio
                    _nfs_import_debug_log(
                        "info",
                        "[NFS_IMPORT_DEBUG] Antes save() lote ABRASF: numero_nota=%s, discriminacao_len=%s, forma_pagamento_id=%s",
                        nfse.numero_nota,
                        len(nfse.discriminacao or ""),
                        getattr(nfse.forma_pagamento, "pk", None),
                    )
                    nfse.save()
                    _nfs_import_debug_log(
                        "info",
                        "[NFS_IMPORT_DEBUG] Após save() lote ABRASF: pk=%s, forma_pagamento_id=%s",
                        nfse.pk,
                        getattr(nfse.forma_pagamento, "pk", None),
                    )
                    safe_print(f"[OK] NFSe {nfse.numero_nota} salva no banco")
                except Exception as e:
                    safe_print(f"[ERRO] Erro ao salvar NFSe {nfse.numero_nota}: {str(e)}")
                    resultado['notas_ignoradas'].append({
                        'numero_nota': nfse.numero_nota,
                        'cliente': nfse.cliente,
                        'motivo': f'Erro ao salvar: {str(e)}'
                    })
                    # Remover da lista de importadas
                    resultado['notas_importadas'] = [n for n in resultado['notas_importadas'] if n['numero_nota'] != nfse.numero_nota]
                    resultado['total_importadas'] -= 1

            tentar_salvar_copia_xml_importacao(
                xml_bytes,
                getattr(xml_file, "name", "nfse.xml") or "nfse.xml",
                empresa,
                root,
                importar_canceladas,
                resultado,
            )
            return resultado
        else:
            print("Detectado: NFSe individual")
            from cobranca.models import Cobranca
            cobrancas = list(Cobranca.objects.all())
            resultado = import_nfse_individual(
                root,
                user,
                empresa,
                cobrancas=cobrancas,
                importar_canceladas=importar_canceladas,
            )
            nfses_retorno = resultado if isinstance(resultado, list) else [resultado]

            nfses_salvas = []
            notas_importadas_list = []
            notas_ignoradas_list = []
            for nfse in nfses_retorno:
                nota_existente = NotaFiscalServico.objects.filter(
                    empresa=empresa,
                    numero_nota=nfse.numero_nota,
                    serie=nfse.serie
                ).first()
                if nota_existente:
                    notas_ignoradas_list.append({
                        'numero_nota': nfse.numero_nota,
                        'cliente': nfse.cliente,
                        'motivo': 'Nota já existe no banco'
                    })
                else:
                    try:
                        if getattr(nfse, "empresa_id", None):
                            socio = extrair_socio(nfse.discriminacao or "", Socio.objects.filter(empresa_id=nfse.empresa_id))
                            if socio:
                                nfse.socio = socio
                        _nfs_import_debug_log(
                            "info",
                            "[NFS_IMPORT_DEBUG] Antes save() ABRASF individual: numero_nota=%s, discriminacao_len=%s, forma_pagamento_id=%s",
                            nfse.numero_nota,
                            len(nfse.discriminacao or ""),
                            getattr(nfse.forma_pagamento, "pk", None),
                        )
                        nfse.save()
                        _nfs_import_debug_log(
                            "info",
                            "[NFS_IMPORT_DEBUG] Após save() ABRASF individual: pk=%s, forma_pagamento_id=%s",
                            nfse.pk,
                            getattr(nfse.forma_pagamento, "pk", None),
                        )
                        safe_print(f"[OK] NFSe {nfse.numero_nota} salva no banco")
                        nfses_salvas.append(nfse)
                        notas_importadas_list.append({
                            'numero_nota': nfse.numero_nota,
                            'cliente': nfse.cliente,
                            'valor_liquido': float(nfse.valor_liquido)
                        })
                    except Exception as e:
                        notas_ignoradas_list.append({
                            'numero_nota': nfse.numero_nota,
                            'cliente': nfse.cliente,
                            'motivo': str(e)
                        })
            resultado_ind = {
                'nfses': nfses_salvas,
                'notas_importadas': notas_importadas_list,
                'notas_ignoradas': notas_ignoradas_list,
                'total_processadas': len(nfses_retorno),
                'total_importadas': len(nfses_salvas),
                'total_ignoradas': len(notas_ignoradas_list)
            }
            tentar_salvar_copia_xml_importacao(
                xml_bytes,
                getattr(xml_file, "name", "nfse.xml") or "nfse.xml",
                empresa,
                root,
                importar_canceladas,
                resultado_ind,
            )
            return resultado_ind

    except ET.ParseError as e:
        safe_print(f"ERRO ParseError: {str(e)}")
        logger.error(f"ParseError no XML: {str(e)}")
        raise ValueError(f"Erro ao processar XML: {str(e)}")
    except Exception as e:
        safe_print(f"ERRO Exception: {str(e)}")
        logger.error(f"Erro inesperado na importação XML: {str(e)}")
        safe_traceback_print_exc()
        raise ValueError(f"Erro inesperado: {str(e)}")

def import_lote_nfse(root, user, empresa, importar_canceladas: bool = False):
    """
    Importa um lote de NFSe
    """
    from cobranca.models import Cobranca
    cobrancas = list(Cobranca.objects.all())

    safe_print("=== DEBUG import_lote_nfse ===")
    safe_print(f"Root tag: {root.tag}")
    
    # Busca especificamente por elementos InfNfse
    nfses = []
    nfse_count = 0
    notas_processadas = set()  # Para evitar duplicatas
    notas_importadas = []
    notas_ignoradas = []
    
    try:
        for infnfse, cancelada in _iter_infnfse_lote_abrasf(root):
            importar_nota = importar_canceladas or cancelada
            try:
                elem_id = id(infnfse)
                if elem_id in notas_processadas:
                    safe_print("[AVISO] Elemento já processado, pulando...")
                    continue
                notas_processadas.add(elem_id)
                nfse_count += 1
                safe_print(f"[OK] InfNfse #{nfse_count} (cancelada={cancelada})")

                resultado = import_nfse_individual(
                    infnfse,
                    user,
                    empresa,
                    cobrancas=cobrancas,
                    importar_canceladas=importar_nota,
                )
                nfses_retorno = resultado if isinstance(resultado, list) else [resultado] if resultado else []
                for nfse in nfses_retorno:
                    if not nfse:
                        continue
                    nota_existente = NotaFiscalServico.objects.filter(
                        empresa=empresa,
                        numero_nota=nfse.numero_nota,
                        serie=nfse.serie
                    ).first()

                    if nota_existente:
                        safe_print(f"[AVISO] NFSe {nfse.numero_nota} já existe no banco, ignorando...")
                        notas_ignoradas.append({
                            'numero_nota': nfse.numero_nota,
                            'cliente': nfse.cliente,
                            'motivo': 'Nota já existe no banco'
                        })
                    else:
                        numero_existente = any(n.numero_nota == nfse.numero_nota and n.serie == nfse.serie for n in nfses)
                        if not numero_existente:
                            nfses.append(nfse)
                            notas_importadas.append({
                                'numero_nota': nfse.numero_nota,
                                'cliente': nfse.cliente,
                                'valor_liquido': float(nfse.valor_liquido)
                            })
                            safe_print(f"[OK] NFSe {nfse.numero_nota} adicionada ao lote")
                        else:
                            safe_print(f"[AVISO] NFSe {nfse.numero_nota} já foi processada no lote, pulando...")
                            notas_ignoradas.append({
                                'numero_nota': nfse.numero_nota,
                                'cliente': nfse.cliente,
                                'motivo': 'Duplicata no XML'
                            })
                if not nfses_retorno:
                    safe_print(f"[ERRO] NFSe não foi criada para InfNfse #{nfse_count}")
            except Exception as e:
                safe_print(f"[ERRO] ERRO ao importar NFSe do InfNfse #{nfse_count}: {str(e)}")
                safe_traceback_print_exc()
                notas_ignoradas.append({
                    'numero_nota': f'InfNfse #{nfse_count}',
                    'cliente': 'Erro na importação',
                    'motivo': str(e)
                })
                continue
        
        print(f"Total de InfNfse encontrados: {len(notas_processadas)}")
        print(f"Total de NFSe importadas com sucesso: {len(nfses)}")
        print(f"Total de NFSe ignoradas: {len(notas_ignoradas)}")

        # Se não conseguiu importar nenhuma NFSe, mas processou algumas, informar o motivo
        if not nfses and notas_processadas:
            safe_print("[ERRO] Nenhuma NFSe pôde ser importada do lote")
            safe_print("Motivos das falhas:")
            for ignorada in notas_ignoradas:
                safe_print(f"  - {ignorada['numero_nota']}: {ignorada['motivo']}")

            # Em vez de lançar erro, retornar resultado vazio mas informativo
            return {
                'nfses': [],
                'notas_importadas': [],
                'notas_ignoradas': notas_ignoradas,
                'total_processadas': len(notas_processadas),
                'total_importadas': 0,
                'total_ignoradas': len(notas_ignoradas)
            }

        # Se não encontrou nenhum InfNfse para processar
        if not notas_processadas:
            safe_print("[ERRO] Nenhum elemento InfNfse encontrado no XML do lote")
            return {
                'nfses': [],
                'notas_importadas': [],
                'notas_ignoradas': [{
                    'numero_nota': 'N/A',
                    'cliente': 'Erro no XML',
                    'motivo': 'Nenhum elemento InfNfse encontrado no lote'
                }],
                'total_processadas': 0,
                'total_importadas': 0,
                'total_ignoradas': 1
            }

        # Retorna um dicionário com as informações do processamento
        return {
            'nfses': nfses,
            'notas_importadas': notas_importadas,
            'notas_ignoradas': notas_ignoradas,
            'total_processadas': len(notas_processadas),
            'total_importadas': len(nfses),
            'total_ignoradas': len(notas_ignoradas)
        }
        
    except Exception as e:
        safe_print(f"ERRO FATAL no import_lote_nfse: {str(e)}")
        safe_traceback_print_exc()
        raise

def import_nfse_individual(
    root,
    user,
    empresa,
    cobrancas: Optional[List] = None,
    importar_canceladas: bool = False,
):
    """
    Importa uma NFSe individual (aceita root nos níveis: CompNfse, Nfse ou InfNfse).
    cobrancas: lista de Cobranca para match de forma_pagamento (evita N+1).
    """
    if cobrancas is None:
        from cobranca.models import Cobranca
        cobrancas = list(Cobranca.objects.all())

    print("=== DEBUG import_nfse_individual ===")
    print(f"Root tag recebida: {root.tag}")
    print(f"Empresa: {empresa.razao} (CNPJ: {empresa.cnpj})")
    print(f"Usuário: {user.username}")
    
    try:
        # Se vier CompNfse/Nfse, desce até InfNfse para ter o escopo correto
        if _local(root.tag) == 'compnfse':
            importar_canceladas = bool(importar_canceladas) or _compnfse_tem_cancelamento(root)

        scope = root
        infnfse_found = False
        
        # Buscar InfNfse em diferentes níveis
        if _local(root.tag) in ['compnfse', 'nfse']:
            for child in root.iter():
                if _local(child.tag) == 'infnfse':
                    scope = child
                    infnfse_found = True
                    safe_print(f"[OK] InfNfse encontrado dentro de {_local(root.tag).upper()}, usando como escopo")
                    break
        else:
            # Se já é InfNfse, usar diretamente
            if _local(root.tag) == 'infnfse':
                scope = root
                infnfse_found = True
                safe_print(f"[OK] Root já é InfNfse, usando diretamente")

        if not infnfse_found:
            safe_print(f"[AVISO] InfNfse não encontrado, usando root como escopo")
        
        # Extrair dados básicos da NFSe
        numero_nota = None
        data_emissao = None
        valor_liquido = None
        cliente = None
        cnpj_cpf = None
        serie = None
        valor_bruto = None
        discriminacao = None
        cnpj_prestador = None
        
        # Campos de impostos e retenções
        valor_deducoes = None
        valor_pis = None
        valor_cofins = None
        valor_inss = None
        valor_ir = None
        valor_csll = None
        tp_ret_pis_cofins = None  # Se "0" ou "2" = zerar PIS, COFINS, CSLL, IR
        tp_ret_issqn = None      # Se "2" e utiliza_iss_fixo=N → ISS retido, valor vISSQN, alíquota pAliqAplic
        iss_retido = False
        valor_iss = None
        valor_iss_retido = None
        outras_retencoes = None
        aliquota = None
        
        print("Buscando dados da NFSe...")
        
        # Buscar especificamente por Numero dentro de InfNfse usando a função corrigida
        numero_nota = find_numero_nota_correct(scope)
        
        # Buscar outros campos
        for elem in scope.iter():
            lname = _local(elem.tag)
            text = (elem.text or '').strip()
            if not text:
                continue
                
            print(f"Tag encontrada: {lname} = {text}")
            
            # Número da NFSe já foi encontrado pela função específica
            if lname == 'numero':
                continue
            elif lname in ('dataemissao', 'dhemi', 'dhEmissao'.lower()):
                data_emissao = text
                print(f"Data de emissão encontrada: {data_emissao}")
            elif lname == 'vliq':
                valor_liquido = text
                print(f"Valor líquido encontrado (vLiq): {valor_liquido}")
            elif valor_liquido is None and lname in ('valorliquidonfse', 'valorliquido', 'valortotal'):
                valor_liquido = text
                print(f"Valor líquido encontrado: {valor_liquido}")
            elif lname == 'serie':
                ctx_serie = get_element_context(elem, scope)
                if ctx_serie not in ('identificacaorps', 'rpssubstituido', 'identificacaorps'):
                    serie = text
                    print(f"Série encontrada: {serie}")
            elif lname == 'vbc':
                valor_bruto = text
                print(f"Valor bruto encontrado (vBC): {valor_bruto}")
            elif lname == 'basecalculo':
                if not valor_bruto:
                    valor_bruto = text
                    print(f"Valor bruto encontrado (BaseCalculo): {valor_bruto}")
            elif valor_bruto is None and lname in ('valorservicos', 'valorservico', 'valortotal', 'valorbruto'):
                valor_bruto = text
                print(f"Valor bruto encontrado: {valor_bruto}")
            elif lname == 'discriminacao':
                discriminacao = text
                print(f"Discriminação encontrada: {discriminacao}")
            # Campos de impostos e retenções
            elif lname == 'valordeducoes':
                valor_deducoes = text
                print(f"Valor deduções encontrado: {valor_deducoes}")
            elif lname == 'valorpis':
                valor_pis = text
                print(f"Valor PIS encontrado: {valor_pis}")
            elif lname == 'valorcofins':
                valor_cofins = text
                print(f"Valor COFINS encontrado: {valor_cofins}")
            elif lname == 'valorinss':
                valor_inss = text
                print(f"Valor INSS encontrado: {valor_inss}")
            elif lname == 'valorir':
                valor_ir = text
                print(f"Valor IR encontrado: {valor_ir}")
            elif lname == 'valorcsll':
                valor_csll = text
                print(f"Valor CSLL encontrado: {valor_csll}")
            elif lname == 'tpretpiscofins':
                tp_ret_pis_cofins = text
                print(f"tpRetPisCofins encontrado: {tp_ret_pis_cofins}")
            elif lname == 'tpretissqn':
                tp_ret_issqn = text
                print(f"tpRetISSQN encontrado: {tp_ret_issqn}")
            elif lname == 'vissqn':
                valor_iss_retido = text
                print(f"Valor vISSQN (ISS retido) encontrado: {valor_iss_retido}")
            elif lname == 'paliqaplic':
                aliquota = text
                print(f"Alíquota pAliqAplic encontrada: {aliquota}")
            elif lname == 'issretido':
                iss_retido = text.strip() in ('1', 'true', 'sim', 's')
                print(f"ISS Retido encontrado: {iss_retido}")
            elif lname == 'valoriss':
                valor_iss = text
                print(f"Valor ISS encontrado: {valor_iss}")
            elif lname == 'valorissretido':
                valor_iss_retido = text
                print(f"Valor ISS Retido encontrado: {valor_iss_retido}")
            elif lname == 'outrasretencoes':
                outras_retencoes = text
                print(f"Outras retenções encontradas: {outras_retencoes}")
            elif lname == 'aliquota':
                aliquota = text
                print(f"Alíquota encontrada: {aliquota}")
        
        print(f"Dados extraídos - Numero: {numero_nota}, Data: {data_emissao}, Valor Bruto: {valor_bruto}, Valor Líquido: {valor_liquido}")

        # Reforço: layout Rio Branco (modelo antigo) — vírgula decimal, BaseCalculo, ValoresNfse
        bruto_scope, liquido_scope = _extrair_valores_nfse_scope(scope)
        if bruto_scope > 0:
            valor_bruto = str(bruto_scope)
        if liquido_scope > 0:
            valor_liquido = str(liquido_scope)
        
        print("Buscando dados do tomador...")
        # Tomador: TomadorServico ou Tomador > (IdentificacaoTomador > CpfCnpj > Cnpj/CPF) + RazaoSocial
        tomador_node = None
        for e in scope.iter():
            try:
                tag_local = _local(e.tag)
                if tag_local in ('tomadorservico', 'tomador'):
                    tomador_node = e
                    safe_print(f"[OK] Tomador encontrado (tag: {tag_local})")
                    break
            except Exception as e:
                safe_print(f"[AVISO] Erro ao buscar tomador: {str(e)}")
                continue
        
        if tomador_node is not None:
            # Razão social
            for raz in tomador_node.iter():
                try:
                    if _local(raz.tag) == 'razaosocial' and (raz.text or '').strip():
                        cliente = raz.text.strip()
                        print(f"Razão social do tomador encontrada: {cliente}")
                        break
                except Exception as e:
                    print(f"Erro ao processar razao social: {str(e)}")
                    continue
            # CNPJ/CPF
            for idt in tomador_node.iter():
                try:
                    if _local(idt.tag) in ('cnpj', 'cpf') and (idt.text or '').strip():
                        cnpj_cpf = idt.text.strip()
                        print(f"Documento do tomador encontrado: {cnpj_cpf}")
                        break
                except Exception as e:
                    print(f"Erro ao processar documento: {str(e)}")
                    continue
        else:
            safe_print(f"[AVISO] TomadorServico não encontrado")
        
        print("Buscando CNPJ da empresa prestadora...")
        print(f"Procurando em scope com tag: {_local(scope.tag)}")
        prestador_node = None
        for e in scope.iter():
            try:
                tag_local = _local(e.tag)
                if tag_local == 'prestadorservico':
                    prestador_node = e
                    safe_print(f"[OK] PrestadorServico encontrado - Tag completa: {e.tag}")
                    break
                elif 'prestador' in tag_local.lower():
                    safe_print(f"[AVISO] Encontrado elemento relacionado a prestador: {tag_local} - Tag: {e.tag}")
            except Exception as e:
                safe_print(f"[AVISO] Erro ao buscar prestador: {str(e)}")
                continue

        if prestador_node is not None:
            # Primeiro tentar encontrar dentro de IdentificacaoPrestador
            identificacao_node = None
            for id_node in prestador_node.iter():
                if _local(id_node.tag) == 'identificacaoprestador':
                    identificacao_node = id_node
                    safe_print(f"[OK] IdentificacaoPrestador encontrado")
                    break

            if identificacao_node is not None:
                # Procurar CNPJ dentro de IdentificacaoPrestador
                for idp in identificacao_node.iter():
                    try:
                        if _local(idp.tag) == 'cnpj' and (idp.text or '').strip():
                            cnpj_prestador = idp.text.strip()
                            print(f"CNPJ da empresa prestadora encontrado em IdentificacaoPrestador: {cnpj_prestador}")
                            break
                    except Exception as e:
                        print(f"Erro ao processar CNPJ prestador: {str(e)}")
                        continue

            # Se não encontrou em IdentificacaoPrestador, procurar diretamente no PrestadorServico
            if not cnpj_prestador:
                for idp in prestador_node.iter():
                    try:
                        if _local(idp.tag) == 'cnpj' and (idp.text or '').strip():
                            cnpj_prestador = idp.text.strip()
                            print(f"CNPJ da empresa prestadora encontrado diretamente em PrestadorServico: {cnpj_prestador}")
                            break
                    except Exception as e:
                        print(f"Erro ao processar CNPJ prestador: {str(e)}")
                        continue
        else:
            safe_print(f"[AVISO] PrestadorServico não encontrado")
        
        # VALIDAÇÃO CNPJ prestador vs empresa
        cnpj_validado = True
        if cnpj_prestador:
            try:
                cnpj_prestador_limpo = limpar_cnpj(cnpj_prestador)
                cnpj_empresa_limpo = limpar_cnpj(empresa.cnpj)
                print(f"DEBUG CNPJ - Original prestador: '{cnpj_prestador}', Limpo: '{cnpj_prestador_limpo}'")
                print(f"DEBUG CNPJ - Original empresa: '{empresa.cnpj}', Limpo: '{cnpj_empresa_limpo}'")

                if cnpj_prestador_limpo != cnpj_empresa_limpo:
                    safe_print(f"[AVISO] AVISO: CNPJ não corresponde: prestador={cnpj_prestador} ({cnpj_prestador_limpo}), empresa={empresa.cnpj} ({cnpj_empresa_limpo})")
                    safe_print("[AVISO] Permitindo importação mesmo com CNPJ diferente (pode ser ajustado manualmente)")
                    cnpj_validado = False
                else:
                    safe_print("[OK] CNPJ validado com sucesso!")
            except Exception as e:
                safe_print(f"[AVISO] ERRO na validação de CNPJ: {str(e)}")
                safe_print("[AVISO] Permitindo importação mesmo com erro na validação CNPJ")
                cnpj_validado = False
        else:
            safe_print("[AVISO] Aviso: CNPJ da empresa prestadora de serviço não encontrado no XML")
            safe_print("[AVISO] Permitindo importação sem validação de CNPJ (CNPJ não encontrado no XML)")
            cnpj_validado = False
        
        # Se não encontrou dados básicos, falhar
        if not numero_nota:
            raise ValueError("Número da nota não encontrado no XML")
        
        if not data_emissao:
            raise ValueError("Data de emissão não encontrada no XML")

        valor_bruto_decimal, valor_liquido_decimal = _extrair_valores_nfse_scope(scope)
        if valor_liquido_decimal <= 0 and valor_bruto_decimal <= 0:
            raise ValueError("Valor líquido não encontrado no XML")
        
        print("Criando objeto NFSe...")
        # Converter data
        data_emissao_parsed = None
        if data_emissao:
            try:
                data_emissao_parsed = parse_date(data_emissao)
                if not data_emissao_parsed and 't' in data_emissao.lower():
                    data_emissao_parsed = datetime.strptime(data_emissao.split('T')[0], '%Y-%m-%d').date()
                print(f"Data convertida: {data_emissao_parsed}")
            except Exception as e:
                print(f"Erro ao converter data: {str(e)}")
                data_emissao_parsed = None
        
        print(f"Valor bruto convertido: {valor_bruto_decimal}")
        print(f"Valor líquido convertido: {valor_liquido_decimal}")
        
        # Converter valores de impostos e retenções
        try:
            valor_deducoes_decimal = _parse_valor_xml(valor_deducoes)
            valor_pis_decimal = _parse_valor_xml(valor_pis)
            valor_cofins_decimal = _parse_valor_xml(valor_cofins)
            valor_inss_decimal = _parse_valor_xml(valor_inss)
            valor_ir_decimal = _parse_valor_xml(valor_ir)
            valor_csll_decimal = _parse_valor_xml(valor_csll)
            valor_iss_retido_decimal = _parse_valor_xml(valor_iss_retido)
            outras_retencoes_decimal = _parse_valor_xml(outras_retencoes)
            aliquota_decimal = _parse_valor_xml(aliquota)
            print(f"Valores de impostos convertidos com sucesso")
        except (ValueError, TypeError) as e:
            print(f"⚠️ Erro ao converter valores de impostos: {str(e)}")
            valor_deducoes_decimal = Decimal('0')
            valor_pis_decimal = Decimal('0')
            valor_cofins_decimal = Decimal('0')
            valor_inss_decimal = Decimal('0')
            valor_ir_decimal = Decimal('0')
            valor_csll_decimal = Decimal('0')
            valor_iss_retido_decimal = Decimal('0')
            outras_retencoes_decimal = Decimal('0')
            aliquota_decimal = Decimal('0')

        # Se tpRetPisCofins 0 ou 2 (operação sem retenção), zerar PIS, COFINS, CSLL e IRPJ
        if tp_ret_pis_cofins in ('0', '2'):
            valor_pis_decimal = Decimal('0')
            valor_cofins_decimal = Decimal('0')
            valor_ir_decimal = Decimal('0')
            valor_csll_decimal = Decimal('0')

        # ISS SPED (tpRetISSQN): regra do portal nacional. ABRASF (Rio Branco) mantém Aliquota/ValorIss do XML.
        if tp_ret_issqn is not None:
            utiliza_iss_fixo = getattr(empresa, "utiliza_iss_fixo", True)
            if utiliza_iss_fixo or tp_ret_issqn != '2':
                iss_retido = False
                valor_iss_retido_decimal = Decimal('0')
                aliquota_decimal = Decimal('0')
        else:
            if valor_iss_retido_decimal > 0:
                iss_retido = True
            elif iss_retido and valor_iss_retido_decimal <= 0 and valor_iss:
                vi = _parse_valor_xml(valor_iss)
                if vi > 0:
                    valor_iss_retido_decimal = vi
        
        # Validar campos obrigatórios
        if not numero_nota:
            raise ValueError("Número da nota é obrigatório")
        if not data_emissao_parsed:
            safe_print("[AVISO] Data de emissão não encontrada, usando data atual")
            data_emissao_parsed = date.today()
        if not valor_bruto_decimal or valor_bruto_decimal <= 0:
            if valor_liquido_decimal and valor_liquido_decimal > 0:
                valor_bruto_decimal = valor_liquido_decimal
                safe_print("[AVISO] Valor bruto não encontrado no XML, usando valor líquido")
            else:
                valor_bruto_decimal = Decimal('0')
                safe_print("[AVISO] Valor bruto inválido, definindo como 0")
        if not valor_liquido_decimal or valor_liquido_decimal <= 0:
            safe_print("[AVISO] Valor líquido inválido, definindo como 0")
            valor_liquido_decimal = Decimal('0')

        # Se é um lote de XMLs de notas canceladas, zerar valores e marcar cancelamento
        if importar_canceladas:
            valor_bruto_decimal = Decimal('0')
            valor_liquido_decimal = Decimal('0')
            valor_deducoes_decimal = Decimal('0')
            valor_pis_decimal = Decimal('0')
            valor_cofins_decimal = Decimal('0')
            valor_inss_decimal = Decimal('0')
            valor_ir_decimal = Decimal('0')
            valor_csll_decimal = Decimal('0')
            valor_iss_retido_decimal = Decimal('0')
            outras_retencoes_decimal = Decimal('0')

        _nfs_import_debug_log(
            "info",
            "[NFS_IMPORT_DEBUG] ABRASF discriminacao extraída: len=%s, primeiros_200=%s",
            len(discriminacao or ""),
            (discriminacao or "")[:200],
        )

        # Preparar dados para criação da NFSe - garantir que não há valores None
        nfse_data = {
            'empresa': empresa,
            'numero_nota': str(numero_nota).strip(),
            'serie': str(serie or '1').strip(),
            'data_emissao': data_emissao_parsed,
            'valor_bruto': valor_bruto_decimal,
            'valor_liquido': valor_liquido_decimal,
            'cliente': str(cliente or 'Cliente não identificado').strip(),
            'cnpj_cpf': str(cnpj_cpf or '').strip(),
            'discriminacao': str(discriminacao or '').strip(),
            # Campos de impostos e retenções
            'valor_deducoes': valor_deducoes_decimal,
            'valor_pis': valor_pis_decimal,
            'valor_cofins': valor_cofins_decimal,
            'valor_inss': valor_inss_decimal,
            'valor_ir': valor_ir_decimal,
            'valor_csll': valor_csll_decimal,
            'iss_retido': bool(iss_retido),
            'valor_iss_retido': valor_iss_retido_decimal,
            'outras_retencoes': outras_retencoes_decimal,
            'aliquota': aliquota_decimal,
            'status_conciliacao': 'nao_conciliado'
        }
        if importar_canceladas:
            # Marca data de cancelamento mantendo a referência da data de emissão
            from datetime import date as _date_cls
            nfse_data['data_cancelamento'] = data_emissao_parsed or _date_cls.today()

        # Verificar se há valores None que podem causar problemas
        for key, value in nfse_data.items():
            if value is None:
                safe_print(f"[AVISO] Campo {key} é None, definindo valor padrão")
                if key == 'data_emissao':
                    nfse_data[key] = date.today()
                    safe_print(f"[OK] Data de emissão definida como hoje: {nfse_data[key]}")
                elif key in ['valor_bruto', 'valor_liquido', 'valor_deducoes', 'valor_pis', 'valor_cofins', 'valor_inss', 'valor_ir', 'valor_csll', 'valor_iss_retido', 'outras_retencoes', 'aliquota']:
                    nfse_data[key] = Decimal('0')
                elif key == 'iss_retido':
                    nfse_data[key] = False
                else:
                    nfse_data[key] = ''

        _nfs_import_debug_log(
            "info",
            "[NFS_IMPORT_DEBUG] ABRASF antes de criar NotaFiscalServico: nfse_data.discriminacao existe=%s, len=%s",
            "discriminacao" in nfse_data and bool(nfse_data.get("discriminacao")),
            len(nfse_data.get("discriminacao") or ""),
        )

        valor_total_nfse = valor_bruto_decimal
        cob, motivo, segmentos = detectar_forma_pagamento_e_vincular(
            discriminacao or "", cobrancas,
            valor_total_nfse=valor_total_nfse,
            valor_liquido_nfse=valor_liquido_decimal,
        )
        if motivo == "multi_segmentar" and segmentos and len(segmentos) >= 2:
            valor_total_seg = sum(seg[0] for seg in segmentos)
            numero_nota = nfse_data["numero_nota"]
            serie = nfse_data["serie"]
            nfses_segmentadas = []
            for i, seg in enumerate(segmentos, 1):
                valor_seg, cob_seg = seg[0], seg[1]
                nsu_seg = seg[2] if len(seg) >= 3 else None
                proporcao = valor_seg / valor_total_seg if valor_total_seg else Decimal("1")
                valor_liq_seg = valor_liquido_decimal * proporcao
                seg_data = dict(nfse_data)
                seg_data["numero_nota"] = "%s-%s" % (numero_nota.strip(), i)
                seg_data["valor_bruto"] = valor_seg
                seg_data["valor_liquido"] = valor_liq_seg
                seg_data["forma_pagamento"] = cob_seg
                seg_data.pop("status_conciliacao", None)
                nfse_seg = NotaFiscalServico(**seg_data)
                nfse_seg.status_conciliacao = "nao_conciliado"
                if nsu_seg is not None:
                    nfse_seg.nsu = nsu_seg
                else:
                    auts = extrair_aut_todos(discriminacao or "")
                    if _eh_forma_cartao(getattr(cob_seg, "descricao", None) or ""):
                        if len(auts) == 1:
                            nfse_seg.nsu = auts[0]
                        elif len(auts) > 1:
                            logger.debug("NFSe %s-%s: multi_aut_detectado (não preenchendo nsu)", numero_nota, i)
                nfses_segmentadas.append(nfse_seg)
            safe_print(f"[OK] NFSe segmentada: {numero_nota} em {len(nfses_segmentadas)} notas")
            return nfses_segmentadas

        try:
            nfse = NotaFiscalServico(**nfse_data)
            safe_print("[OK] NFSe criada com sucesso!")
        except TypeError as te:
            safe_print(f"[ERRO] ERRO TypeError ao criar NFSe: {str(te)}")
            safe_print(f"Dados que tentei passar: {list(nfse_data.keys())}")
            safe_print("Verifique se todos os campos existem no modelo NotaFiscalServico")
            raise

        nfse.forma_pagamento = cob if cob else None
        forma_unica = extrair_forma_pagamento(discriminacao or "") if discriminacao else None
        auts = extrair_aut_todos(discriminacao or "")
        if forma_unica and _eh_forma_cartao(forma_unica):
            if len(auts) == 1:
                nfse.nsu = (auts[0] or "").strip().rstrip(".,;")
                safe_print(f"NSU extraído da discriminação: {nfse.nsu}")
            elif len(auts) > 1:
                logger.debug("NFSe %s: multi_aut_detectado (não preenchendo nsu)", nfse.numero_nota)
        else:
            nfse.nsu = None
        if not cob and motivo not in ("nao_identificado",):
            logger.debug("NFSe %s forma_pagamento não vinculado: %s", nfse.numero_nota, motivo)

        _nfs_import_debug_log(
            "info",
            "[NFS_IMPORT_DEBUG] ABRASF antes de retornar nfse: numero_nota=%s, discriminacao_len=%s, forma_pagamento_id=%s",
            nfse.numero_nota,
            len(nfse.discriminacao or ""),
            getattr(nfse.forma_pagamento, "pk", None),
        )
        safe_print(f"[OK] NFSe criada com sucesso: {nfse.numero_nota}")
        safe_print(f"Cliente: {nfse.cliente}, CNPJ/CPF: {nfse.cnpj_cpf}")
        return nfse

    except Exception as e:
        safe_print(f"ERRO FATAL no import_nfse_individual: {str(e)}")
        safe_traceback_print_exc()
        raise


def aplicar_nfse_importada_em_existente(destino: NotaFiscalServico, origem: NotaFiscalServico) -> None:
    """Atualiza NFSe existente com dados parseados do XML (valores, retenções, status)."""
    destino.data_cancelamento = None
    destino.serie = origem.serie or destino.serie or '1'
    destino.data_emissao = origem.data_emissao or destino.data_emissao
    destino.valor_bruto = origem.valor_bruto
    destino.valor_liquido = origem.valor_liquido
    destino.cliente = origem.cliente or destino.cliente
    destino.cnpj_cpf = origem.cnpj_cpf or destino.cnpj_cpf
    destino.discriminacao = origem.discriminacao or destino.discriminacao
    destino.valor_deducoes = origem.valor_deducoes
    destino.valor_pis = origem.valor_pis
    destino.valor_cofins = origem.valor_cofins
    destino.valor_inss = origem.valor_inss
    destino.valor_ir = origem.valor_ir
    destino.valor_csll = origem.valor_csll
    destino.iss_retido = origem.iss_retido
    destino.valor_iss_retido = origem.valor_iss_retido
    destino.outras_retencoes = origem.outras_retencoes
    destino.aliquota = origem.aliquota
    if origem.forma_pagamento_id:
        destino.forma_pagamento = origem.forma_pagamento
    if origem.nsu:
        destino.nsu = origem.nsu
    destino.save()
    from contasareceber.socio_sync import (
        propagar_autorizacao_nota_para_contas_receber,
        propagar_forma_pagamento_nota_para_contas_receber,
    )
    propagar_forma_pagamento_nota_para_contas_receber(destino)
    propagar_autorizacao_nota_para_contas_receber(destino, apenas_vazias=False)


def parse_date(date_str):
    """
    Tenta converter uma string de data para um objeto date
    """
    if not date_str:
        return None

    # Remove espaços e caracteres especiais
    date_str = date_str.strip()

    # Primeiro tenta usar dateutil que é mais flexível
    try:
        parsed_date = date_parser.parse(date_str)
        return parsed_date.date()
    except:
        pass

    # Padrões de data comuns como fallback
    patterns = [
        '%Y-%m-%d',           # 2025-01-15
        '%d/%m/%Y',           # 15/01/2025
        '%d-%m-%Y',           # 15-01-2025
        '%Y/%m/%d',           # 2025/01/15
        '%d/%m/%y',           # 15/01/25
        '%d-%m-%y',           # 15-01-25
        '%Y-%m-%dT%H:%M:%S', # 2025-01-15T10:30:00
        '%Y-%m-%d %H:%M:%S', # 2025-01-15 10:30:00
    ]

    for pattern in patterns:
        try:
            return datetime.strptime(date_str, pattern).date()
        except ValueError:
            continue

    # Se nenhum padrão funcionar, retorna None
    safe_print(f"[AVISO] Não foi possível converter a data: {date_str}")
    return None

def extract_xml_data_preview(xml_file, empresa):
    """
    Extrai dados das notas para preview sem salvar no banco
    """
    nome = getattr(xml_file, "name", "") or "nota.xml"
    if _conteudo_xml_vazio(xml_file):
        return [preview_arquivo_vazio(nome)]

    try:
        try:
            root = _parse_xml_root(xml_file)
        except OSError as os_err:
            # Trata especificamente erros de sistema de arquivos (como [Errno 22] Invalid argument)
            safe_print(f"[ERRO] Erro de sistema de arquivos ao abrir XML para preview: {str(os_err)}")
            safe_print(f"[ERRO] Nome do arquivo: '{xml_file.name}'")
            safe_print(f"[ERRO] Tipo de erro: {type(os_err).__name__}")
            if hasattr(os_err, 'errno'):
                safe_print(f"[ERRO] Código do erro: {os_err.errno}")
            # Log adicional para debug
            logger.error(f"OSError ao abrir XML para preview: arquivo='{xml_file.name}', erro='{str(os_err)}', errno={getattr(os_err, 'errno', 'N/A')}")
            raise ValueError(f"Erro ao acessar arquivo XML: {str(os_err)}. Verifique se o nome do arquivo contém caracteres especiais ou se o arquivo está corrompido.")
        except ET.ParseError as parse_err:
            safe_print(f"[ERRO] Erro de parsing XML para preview: {str(parse_err)}")
            safe_print(f"[ERRO] Arquivo pode estar corrompido ou ter formato inválido")
            raise ValueError(f"Erro ao processar XML: {str(parse_err)}")
        except ValueError:
            raise

        from notasfiscais.nfse_evento_cancelamento import (
            extract_evento_cancelamento_preview,
            is_evento_cancelamento_nfse,
        )
        if is_evento_cancelamento_nfse(root):
            return extract_evento_cancelamento_preview(root, empresa)
        
        if _is_nfse_sped(root):
            return extract_sped_preview(root, empresa)
        if _local(root.tag) in ("consultarnfselote", "listanfse", "lotenotafiscal"):
            return extract_lote_preview(root, empresa)
        else:
            return [extract_nota_individual_preview(root, empresa)]
            
    except Exception as e:
        logger.warning("Erro ao extrair preview XML: %s", e)
        return []


def extract_sped_preview(root, empresa):
    """
    Extrai preview das notas de um XML SPED (Portal Nacional).
    Retorna lista de dict com numero_nota, serie, data_emissao, valor_bruto, valor_liquido, cliente, cnpj_cpf, discriminacao, etc.
    """
    ns = NS_SPED
    tag_inf = _qname(ns, "infNFSe")
    inf_list = root.findall(".//%s" % tag_inf)
    if not inf_list:
        inf_one = root.find(tag_inf)
        if inf_one is not None:
            inf_list = [inf_one]

    notas_preview = []
    for infnfse in inf_list:
        try:
            numero_nota = _t(infnfse, "nNFSe", ns)
            if not numero_nota:
                continue
            serie = _t(infnfse, "DPS/infDPS/serie", ns) or "1"
            data_emissao = (
                _d(infnfse, "dhProc", ns)
                or _d(infnfse, "dhEmi", ns)
                or _d(infnfse, "DPS/infDPS/dhEmi", ns)
            )
            data_str = data_emissao.strftime("%Y-%m-%d") if data_emissao else ""
            valor_bruto = _dec_primeiro(infnfse, [
                "valores/vBC",
                "valores/vServPrest/vServ",
                "DPS/infDPS/valores/vServPrest/vServ",
            ], ns=ns)
            valor_liq = _dec_primeiro(infnfse, ["valores/vLiq", "DPS/infDPS/valores/vLiq"], ns=ns)
            valor_liquido = valor_liq if valor_liq > 0 else valor_bruto
            if not valor_bruto or valor_bruto <= 0:
                valor_bruto = valor_liquido
            cliente = _t_primeiro(infnfse, ["DPS/infDPS/toma/xNome", "toma/xNome"], ns=ns) or "Cliente não identificado"
            cnpj_cpf = _t_primeiro(infnfse, [
                "DPS/infDPS/toma/CNPJ", "DPS/infDPS/toma/CPF", "toma/CNPJ", "toma/CPF",
            ], ns=ns) or ""
            discriminacao = _t_primeiro(infnfse, [
                "serv/cServ/xDescServ",
                "DPS/infDPS/serv/cServ/xDescServ",
            ], ns=ns) or ""
            ibscbs = _extrair_ibscbs_sped(infnfse)
            # Preview simples de base de serviço (usar NORMAL por padrão no preview;
            # o cálculo definitivo é feito em determinar_base_servico() ao salvar a NFSe)
            base_servico_preview = "Normal"
            nota = {
                "numero_nota": numero_nota,
                "serie": serie,
                "data_emissao": data_str,
                "valor_bruto": str(valor_bruto),
                "valor_liquido": str(valor_liquido),
                "cliente": cliente,
                "cnpj_cpf": cnpj_cpf,
                "discriminacao": discriminacao,
                "base_servico": base_servico_preview,
                "base_ibs_cbs": str(ibscbs.get("base_ibs_cbs") or 0),
                "valor_ibs": str(ibscbs.get("valor_ibs") or 0),
                "valor_cbs": str(ibscbs.get("valor_cbs") or 0),
                "cnpj_prestador": None,
                "cnpj_valido": True,
                "status": "valido",
            }
            if not any(
                n.get("numero_nota") == nota["numero_nota"] and n.get("serie") == nota["serie"]
                for n in notas_preview
            ):
                notas_preview.append(nota)
        except Exception as e:
            logger.warning("Erro ao extrair preview infNFSe SPED: %s", e)
            continue
    return notas_preview

def extract_lote_preview(root, empresa):
    """
    Extrai preview de um lote de NFSe
    """
    notas_preview = []
    notas_processadas = set()  # Para evitar duplicatas
    
    print("=== DEBUG extract_lote_preview ===")
    print(f"Root tag: {root.tag}")
    
    # Buscar especificamente por elementos InfNfse
    try:
        for infnfse, cancelada in _iter_infnfse_lote_abrasf(root):
            elem_id = id(infnfse)
            if elem_id in notas_processadas:
                continue
            notas_processadas.add(elem_id)

            try:
                nota = extract_nota_individual_preview(infnfse, empresa, importar_canceladas=cancelada)
                if nota and nota.get('numero_nota'):
                    numero_existente = any(
                        n.get('numero_nota') == nota['numero_nota'] and n.get('serie') == nota['serie']
                        for n in notas_preview
                    )
                    if not numero_existente:
                        notas_preview.append(nota)
            except Exception as e:
                print(f"Erro ao extrair preview da NFSe InfNfse: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"Total de InfNfse encontrados: {len(notas_processadas)}")
        print(f"Total de previews únicos criados: {len(notas_preview)}")
        
        return notas_preview
        
    except Exception as e:
        safe_print(f"ERRO FATAL no extract_lote_preview: {str(e)}")
        safe_traceback_print_exc()
        return []

def extract_nota_individual_preview(root, empresa, importar_canceladas: bool = False):
    """
    Extrai preview de uma NFSe individual para exibição
    """
    print("=== DEBUG extract_nota_individual_preview ===")
    
    # Se vier CompNfse/Nfse, desce até InfNfse para ter o escopo correto
    scope = root
    infnfse_found = False
    
    # Buscar InfNfse em diferentes níveis
    if _local(root.tag) in ['compnfse', 'nfse']:
        for child in root.iter():
            if _local(child.tag) == 'infnfse':
                scope = child
                infnfse_found = True
                safe_print(f"[OK] InfNfse encontrado dentro de {_local(root.tag).upper()}, usando como escopo")
                break
    else:
        # Se já é InfNfse, usar diretamente
        if _local(root.tag) == 'infnfse':
            scope = root
            infnfse_found = True
            safe_print(f"[OK] Root já é InfNfse, usando diretamente")

    if not infnfse_found:
        safe_print(f"[AVISO] InfNfse não encontrado, usando root como escopo")
    
    # Extrair dados básicos da NFSe
    numero_nota = None
    data_emissao = None
    valor_liquido = None
    cliente = None
    cnpj_cpf = None
    serie = None
    valor_bruto = None
    discriminacao = None
    cnpj_prestador = None
    
    print("Buscando dados da NFSe para preview...")
    
    # Buscar especificamente por Numero dentro de InfNfse usando a função corrigida
    numero_nota = find_numero_nota_correct(scope)
    
    # Buscar outros campos
    for elem in scope.iter():
        lname = _local(elem.tag)
        text = (elem.text or '').strip()
        if not text:
            continue
            
        print(f"Tag encontrada: {lname} = {text}")
        
        # Número da NFSe já foi encontrado pela função específica
        if lname == 'numero':
            continue
        elif lname in ('dataemissao', 'dhemi', 'dhEmissao'.lower()):
            data_emissao = text
            print(f"Data de emissão encontrada: {data_emissao}")
        elif lname == 'vliq':
            valor_liquido = text
            print(f"Valor líquido encontrado (vLiq): {valor_liquido}")
        elif valor_liquido is None and lname in ('valorliquidonfse', 'valorliquido', 'valortotal'):
            valor_liquido = text
            print(f"Valor líquido encontrado: {valor_liquido}")
        elif lname == 'serie':
            serie = text
            print(f"Série encontrada: {serie}")
        elif lname == 'vbc':
            valor_bruto = text
            print(f"Valor bruto encontrado (vBC): {valor_bruto}")
        elif lname == 'basecalculo':
            if not valor_bruto:
                valor_bruto = text
                print(f"Valor bruto encontrado (BaseCalculo): {valor_bruto}")
        elif valor_bruto is None and lname in ('valorservicos', 'valorservico', 'valortotal', 'valorbruto', 'vserv'):
            valor_bruto = text
            print(f"Valor bruto encontrado: {valor_bruto}")
        elif lname == 'discriminacao':
            discriminacao = text
            print(f"Discriminação encontrada: {discriminacao}")
    
    bruto_preview, liquido_preview = _extrair_valores_nfse_scope(scope)
    if bruto_preview > 0:
        valor_bruto = bruto_preview
    if liquido_preview > 0:
        valor_liquido = liquido_preview
    
    print(f"Dados extraídos para preview - Numero: {numero_nota}, Data: {data_emissao}, Valor Bruto: {valor_bruto}, Valor Líquido: {valor_liquido}")
    
    print("Buscando dados do tomador para preview...")
    # Tomador: TomadorServico ou Tomador > (IdentificacaoTomador > CpfCnpj > Cnpj/CPF) + RazaoSocial
    tomador_node = None
    for e in scope.iter():
        tag_local = _local(e.tag)
        if tag_local in ('tomadorservico', 'tomador'):
            tomador_node = e
            safe_print(f"[OK] Tomador encontrado (tag: {tag_local})")
            break
    
    if tomador_node is not None:
        # Razão social
        for raz in tomador_node.iter():
            if _local(raz.tag) == 'razaosocial' and (raz.text or '').strip():
                cliente = raz.text.strip()
                print(f"Razão social do tomador encontrada: {cliente}")
                break
        # CNPJ/CPF
        for idt in tomador_node.iter():
            if _local(idt.tag) in ('cnpj', 'cpf') and (idt.text or '').strip():
                cnpj_cpf = idt.text.strip()
                print(f"Documento do tomador encontrado: {cnpj_cpf}")
                break
    else:
        safe_print(f"[AVISO] TomadorServico não encontrado")
    
    print("Buscando CNPJ da empresa prestadora para preview...")
    prestador_node = None
    for e in scope.iter():
        if _local(e.tag) == 'prestadorservico':
            prestador_node = e
            safe_print(f"[OK] PrestadorServico encontrado")
            break
    
    if prestador_node is not None:
        for idp in prestador_node.iter():
            if _local(idp.tag) == 'cnpj' and (idp.text or '').strip():
                cnpj_prestador = idp.text.strip()
                print(f"CNPJ da empresa prestadora encontrado: {cnpj_prestador}")
                break
    else:
        safe_print(f"[AVISO] PrestadorServico não encontrado")
    
    # Se não encontrou dados básicos, retornar None
    if not numero_nota:
        safe_print("[ERRO] ERRO: Número da nota não encontrado para preview")
        safe_print(f"Debug - Scope tag: {_local(scope.tag)}")
        safe_print(f"Debug - Elementos encontrados no scope:")
        for elem in scope.iter():
            try:
                lname = _local(elem.tag)
                text = (elem.text or '').strip()
                if text:
                    safe_print(f"  - {lname}: {text}")
            except:
                continue
        return None
    
    # VALIDAÇÃO CNPJ prestador vs empresa (mais tolerante para preview)
    cnpj_valido = False
    if cnpj_prestador:
        try:
            cnpj_prestador_limpo = limpar_cnpj(cnpj_prestador)
            cnpj_empresa_limpo = limpar_cnpj(empresa.cnpj)
            print(f"DEBUG CNPJ Preview - Original prestador: '{cnpj_prestador}', Limpo: '{cnpj_prestador_limpo}'")
            print(f"DEBUG CNPJ Preview - Original empresa: '{empresa.cnpj}', Limpo: '{cnpj_empresa_limpo}'")
            cnpj_valido = cnpj_prestador_limpo == cnpj_empresa_limpo
            if cnpj_valido:
                safe_print("[OK] CNPJ validado com sucesso para preview!")
            else:
                safe_print("[AVISO] CNPJ não corresponde para preview (mas permitindo preview)")
                cnpj_valido = False  # Para preview, marcamos como inválido mas não impedimos
        except Exception as e:
            safe_print(f"[AVISO] Erro ao validar CNPJ para preview: {str(e)}")
            cnpj_valido = False
    else:
        safe_print("[AVISO] Aviso: CNPJ da empresa prestadora de serviço não encontrado no XML para preview")
        # Para preview, não vamos falhar se não encontrar CNPJ
    
    # Fallback: se valor bruto não foi encontrado, usar valor líquido
    if not valor_bruto and valor_liquido:
        valor_bruto = valor_liquido

    if importar_canceladas:
        valor_bruto = 0
        valor_liquido = 0

    # Retornar dados para preview (status usado no template para Válida/Inválida)
    return {
        'numero_nota': numero_nota,
        'serie': serie or '1',
        'data_emissao': data_emissao,
        'valor_bruto': valor_bruto,
        'valor_liquido': valor_liquido,
        'cliente': cliente or 'Cliente não identificado',
        'cnpj_cpf': cnpj_cpf or '',
        'discriminacao': discriminacao or '',
        'cnpj_prestador': cnpj_prestador,
        'cnpj_valido': cnpj_valido,
        'status': 'cancelada' if importar_canceladas else ('valido' if cnpj_valido else 'invalido'),
        'importar_cancelada': importar_canceladas,
    }




