"""
Cópia em disco dos XML de NFSe após importação bem-sucedida.

Estrutura (a partir da pasta configurada para prestador ou tomador):
  {codigo_externo}-{razao_social}/{MMYYYY}/{nome_arquivo}.xml
Notas importadas como canceladas (checkbox) — cópias na pasta da EMPRESA:
  {codigo_externo}-{razão da empresa}/{MMYYYY}/Cancelada/{nome_arquivo}.xml

- Prestador (empresa = emitente no XML): pasta do prestador; subpasta = tomador
  (cadastro Cliente: codigo_externo + razao; senão 0 + razão do XML).
- Tomador (empresa = tomador no XML): pasta do tomador; subpasta = prestador
  (cadastro Fornecedor: codigo_externo + razao; senão 0 + razão do XML).

A pasta ``Cancelada`` é usada quando o checkbox «importar como canceladas» está ativo **ou** quando o
próprio XML indica nota cancelada (evento / situação no layout nacional SPED).

Competência: tag dCompet (SPED) quando existir; senão data de emissão da primeira nota importada (MMYYYY).

Pastas ``{codigo}-{razão}/{MMYYYY}/`` (e ``Cancelada`` quando aplicável) são criadas automaticamente se ainda não existirem.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

# Padrões no XML nacional (SPED / eventos) que indicam cancelamento da NFS-e.
_RE_CSITNFE_CANCEL = re.compile(r"<[^>]*cSitNFe[^>]*>\s*([23])\s*</", re.I)
_RE_INF_CANC = re.compile(r"<[^>]*infCanc[^>]*>", re.I)
_RE_ABRASF_LAYOUT = re.compile(
    r"abrasf\.org\.br|ginfes\.com\.br|<[^>]*compnfse|<[^>]*listanfse|<[^>]*lotenotafiscal",
    re.I,
)
_RE_ABRASF_CANCELAMENTO = re.compile(
    r"<[^>]*(nfsecancelamento|infpedidocancelamento|confirmacaocancelamento|retcancelamento)[^>]*>",
    re.I,
)


def _xml_layout_abrasf_municipal(raw: str) -> bool:
    """True se o XML é NFS-e municipal (ABRASF/Ginfes), não portal nacional SPED."""
    if not raw:
        return False
    return bool(_RE_ABRASF_LAYOUT.search(raw))


def abrasf_xml_indica_cancelada(xml_bytes: bytes) -> bool:
    """
    Cancelamento explícito em XML ABRASF (Rio Branco e similares).
    Não usa palavras soltas na discriminação — só tags de evento/pedido de cancelamento.
    """
    if not xml_bytes or len(xml_bytes) < 80:
        return False
    try:
        raw = xml_bytes.decode("utf-8", errors="replace")
    except Exception:
        return False
    return bool(_RE_ABRASF_CANCELAMENTO.search(raw))


def xml_nfse_portal_indica_cancelada(xml_bytes: bytes) -> bool:
    """
    Heurística para XML baixado do portal nacional: evento de cancelamento ou situação cancelada.

    Usado para gravar cópias em ``…/Cancelada/`` e para importar com valores zerados sem depender só do checkbox.
    Não se aplica a XML ABRASF municipal (Rio Branco) — use ``abrasf_xml_indica_cancelada``.
    """
    if not xml_bytes or len(xml_bytes) < 80:
        return False
    try:
        raw = xml_bytes.decode("utf-8", errors="replace")
    except Exception:
        return False
    if _xml_layout_abrasf_municipal(raw):
        return abrasf_xml_indica_cancelada(xml_bytes)
    low = raw.lower().replace("\n", " ")
    if _RE_INF_CANC.search(raw):
        return True
    if "pedregevento" in low and "cancel" in low:
        return True
    if "cancelamento" in low and ("nfs-e" in low or "sped" in low):
        return True
    m = _RE_CSITNFE_CANCEL.search(raw)
    if m:
        return True
    if re.search(r"<[^>]*sit[^>]*nfse[^>]*>\s*2\s*</", raw, re.I):
        return True
    if "p104_nfse_cancelada" in low:
        return True
    return False


def html_extensao_portal_indica_nfse_cancelada(html_bytes: bytes) -> bool:
    """
    HTML guardado pela extensão / página «Emitidas»: atributos ``data-situacao``, ``data-original-title``,
    ícone ``tb-cancelada.svg``, etc.
    """
    if not html_bytes or len(html_bytes) < 40:
        return False
    try:
        raw = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return False
    low = raw.lower()
    compact = re.sub(r"\s+", "", low)
    if "p104_nfse_cancelada" in compact:
        return True
    if "tb-cancelada.svg" in low:
        return True
    if re.search(r"data-situacao\s*=\s*[\"'][^\"']*cancel[^\"']*nfse", low, re.I):
        return True
    if "data-original-title" in low and "cancel" in low and ("nfse" in low or "nfs-e" in low):
        return True
    if "td-situacao" in low and "cancel" in low:
        return True
    return False


def extrair_chave_acesso_nfse_html(html_bytes: bytes) -> Optional[str]:
    """44 dígitos no HTML (corpo ou atributos); ``data-chave`` costuma ser outro formato."""
    if not html_bytes:
        return None
    try:
        blob = re.sub(r"\s+", "", html_bytes.decode("utf-8", errors="replace")[:200000])
    except Exception:
        return None
    m = re.search(r"(?<![0-9])(\d{44})(?![0-9])", blob)
    return m.group(1) if m else None


def portal_emitidas_data_situacao_indica_cancelada(situacao: str) -> bool:
    """
    Situação vinda do atributo ``data-situacao`` na linha da grelha «Emitidas» do Emissor Nacional
    (ex.: ``P104_NFSE_CANCELADA`` vs ``P100_GERADA``).
    """
    s = (situacao or "").strip().upper()
    if not s:
        return False
    if "P104" in s and "CANCEL" in s:
        return True
    if "CANCELADA" in s and "NFSE" in s:
        return True
    return False


# Manifesto escrito pelo Selenium na pasta de downloads (chaves canceladas + web_chave para evitar repetir).
PORTAL_EMITIDAS_MANIFEST_NAME = "._nfse_emitidas_portal.json"


def extrair_chave_acesso_nfse_xml(xml_bytes: bytes) -> Optional[str]:
    """Primeira chave de acesso com 44 dígitos encontrada no XML (Portal nacional / SPED)."""
    if not xml_bytes:
        return None
    try:
        raw = xml_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None
    blob = re.sub(r"\s+", "", raw[:200000])
    m = re.search(r"(?<![0-9])(\d{44})(?![0-9])", blob)
    return m.group(1) if m else None


def emitidas_portal_manifest_caminho(pasta: Path | str) -> Path:
    return Path(pasta) / PORTAL_EMITIDAS_MANIFEST_NAME


def emitidas_portal_manifest_limpar(pasta: Path | str) -> None:
    p = emitidas_portal_manifest_caminho(pasta)
    if p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


def emitidas_portal_manifest_carregar(pasta: Path | str) -> dict[str, Any]:
    p = emitidas_portal_manifest_caminho(pasta)
    if not p.is_file():
        return {"canceladas_chave44": [], "web_chave_baixadas": [], "chaves44_baixadas": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return {"canceladas_chave44": [], "web_chave_baixadas": [], "chaves44_baixadas": []}
        cc = d.get("canceladas_chave44") or []
        wb = d.get("web_chave_baixadas") or []
        k44 = d.get("chaves44_baixadas") or []
        return {
            "canceladas_chave44": cc if isinstance(cc, list) else [],
            "web_chave_baixadas": wb if isinstance(wb, list) else [],
            "chaves44_baixadas": k44 if isinstance(k44, list) else [],
        }
    except Exception:
        return {"canceladas_chave44": [], "web_chave_baixadas": [], "chaves44_baixadas": []}


def emitidas_portal_manifest_gravar(pasta: Path | str, data: dict[str, Any]) -> None:
    p = emitidas_portal_manifest_caminho(pasta)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def emitidas_portal_manifest_append(
    pasta: Path | str,
    *,
    chave44: Optional[str] = None,
    cancelada_portal: bool = False,
    web_chave: Optional[str] = None,
) -> None:
    """
    Acrescenta ``data-chave`` da linha (web_chave), chave 44 de **toda** NF já baixada (evitar repetir download),
    e chave 44 na lista de canceladas quando ``cancelada_portal``.
    """
    data = emitidas_portal_manifest_carregar(pasta)
    ck = (chave44 or "").strip()
    kall = data.get("chaves44_baixadas")
    if not isinstance(kall, list):
        kall = []
        data["chaves44_baixadas"] = kall
    if ck and ck not in kall:
        kall.append(ck)
    if ck and cancelada_portal and ck not in data["canceladas_chave44"]:
        data["canceladas_chave44"].append(ck)
    wk = (web_chave or "").strip()
    if wk and wk not in data["web_chave_baixadas"]:
        data["web_chave_baixadas"].append(wk)
    emitidas_portal_manifest_gravar(pasta, data)


def emitidas_portal_manifest_chaves_canceladas(pasta: Path | str) -> set[str]:
    d = emitidas_portal_manifest_carregar(pasta)
    return {str(x).strip() for x in d["canceladas_chave44"] if str(x).strip()}


def emitidas_portal_manifest_web_chave_ja_listada(pasta: Path | str, web_chave: str) -> bool:
    if not (web_chave or "").strip():
        return False
    d = emitidas_portal_manifest_carregar(pasta)
    return web_chave.strip() in set(d["web_chave_baixadas"])


def emitidas_portal_manifest_chave44_ja_baixada(pasta: Path | str, chave44: str) -> bool:
    """Chave de acesso (44 dígitos) já registada nesta execução/pasta (manifesto Selenium)."""
    c = (chave44 or "").strip()
    if len(c) != 44 or not c.isdigit():
        return False
    d = emitidas_portal_manifest_carregar(pasta)
    return c in {str(x).strip() for x in d.get("chaves44_baixadas", []) if str(x).strip()}


class PastaNfseInacessivelError(Exception):
    """A raiz configurada para cópias XML (prestador) ou a pasta de downloads do portal não existe ou não tem permissão de escrita."""


def _limpar_doc(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def _sanitizar_segmento_pasta(nome: str, max_len: int = 100) -> str:
    if not nome:
        return "SemNome"
    n = nome.strip()
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", n)
    n = re.sub(r"\s+", " ", n).strip()
    n = n.strip(". ")
    if not n:
        return "SemNome"
    return n[:max_len]


def _normalizar_pasta_mesano(compet_pasta: Optional[str], fallback: date) -> str:
    """
    Nome da subpasta por competência/emissão no padrão MMYYYY (ex.: 012026, 042026).
    Se o valor vindo do XML for inválido, usa a data de fallback.
    """
    s = (compet_pasta or "").strip().replace(" ", "").replace("/", "").replace("-", "")
    if re.fullmatch(r"\d{6}", s):
        mm = int(s[:2])
        yyyy = int(s[2:])
        if 1 <= mm <= 12 and 2000 <= yyyy <= 2099:
            return f"{mm:02d}{yyyy}"
    return f"{fallback.month:02d}{fallback.year}"


def _garantir_pasta_copia_nfse(dest_dir: Path) -> None:
    """Cria a pasta de destino (e pais), inclusive a subpasta mês/ano, se ainda não existir."""
    dest = Path(dest_dir)
    nova = not dest.exists()
    dest.mkdir(parents=True, exist_ok=True)
    if nova:
        logger.info("Pasta de cópia NFSe criada: %s", dest)


def _nfse_xml_base_prestador(empresa) -> str:
    d = getattr(settings, "NFSE_XML_COPIA_PRESTADOR", "") or ""
    return (getattr(empresa, "nfse_xml_pasta_prestador", None) or "").strip() or (d or "").strip()


def _nfse_xml_base_tomador(empresa) -> str:
    d = getattr(settings, "NFSE_XML_COPIA_TOMADOR", "") or ""
    return (getattr(empresa, "nfse_xml_pasta_tomador", None) or "").strip() or (d or "").strip()


def validar_periodo_um_mes_portal_nacional(di: date, df: date) -> None:
    """Downloads do portal ficam em subpasta MMAAAA; o período tem de ser um único mês civil."""
    if di > df:
        raise ValueError("A data inicial não pode ser maior que a data final.")
    if (di.year, di.month) != (df.year, df.month):
        raise ValueError(
            "Para gravar os downloads em «código externo-razão/MMAAAA» (ex.: 188-EMPRESA/042026), "
            "a data inicial e a data final devem estar no mesmo mês civil "
            "(ex.: 01/04/2026 a 30/04/2026)."
        )


def _segmento_pasta_empresa_codigo_razao(empresa) -> str:
    """Nome da pasta da empresa: ``{codigo_externo}-{razão}`` (emitidas / inbox / canceladas)."""
    codigo = (getattr(empresa, "codigo_externo", None) or "").strip() or "0"
    razao = _sanitizar_segmento_pasta(getattr(empresa, "razao", None) or "Empresa")
    return f"{codigo}-{razao}"


def _pasta_prestador_codigo_razao_mes(empresa, competencia: date) -> Path:
    """Segmento relativo: ``{codigo_externo}-{razão}/{MMYYYY}`` (emitidas / pasta prestador)."""
    mmyyyy = f"{competencia.month:02d}{competencia.year}"
    return Path(_segmento_pasta_empresa_codigo_razao(empresa)) / mmyyyy


def pasta_inbox_downloads_portal_nacional(
    empresa, data_inicio: date, data_fim: date
) -> Optional[Path]:
    """
    Pasta onde o Selenium (ou importação manual) grava XML/PDF brutos antes do processamento.

    Usa a raiz «prestador» (campo da empresa ou ``NFSE_XML_COPIA_PRESTADOR``), por exemplo
    ``X:\\...\\PRESTADOS``, e dentro cria automaticamente::

        {codigo_externo}-{razão social}/{MMYYYY}/

    em que ``MMYYYY`` corresponde ao mês civil de ``data_inicio`` (tem de ser o mesmo mês de ``data_fim``).

    Se a raiz não estiver acessível, levanta :exc:`PastaNfseInacessivelError`.
    Se o período abranger mais de um mês, levanta :exc:`ValueError`.
    """
    base = (_nfse_xml_base_prestador(empresa) or "").strip()
    if not base:
        return None

    validar_periodo_um_mes_portal_nacional(data_inicio, data_fim)
    rel = _pasta_prestador_codigo_razao_mes(empresa, data_inicio)
    p = Path(base).expanduser() / rel
    try:
        p.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            raise OSError("A pasta não foi criada.")
        logger.info("Pasta downloads portal NFSe (prestador/mês): %s", p)
        return p.resolve()
    except (OSError, FileNotFoundError, ValueError) as e:
        logger.error("Pasta de downloads portal NFSe inacessível: %s — %s", p, e)
        raise PastaNfseInacessivelError(
            "Não foi possível criar ou aceder à pasta de downloads do portal NFSe:\n"
            f"  {p}\n"
            f"Motivo: {e}\n"
            "Confirme que a unidade de disco (ex.: X:) está mapeada, que o caminho de rede está ligado "
            "e que há permissão de escrita. Ajuste «Pasta cópias XML NFSe (prestador)» em Configuração de integração "
            "(ou a variável NFSE_XML_COPIA_PRESTADOR no servidor)."
        ) from e


def _doc_match_variants(doc: str) -> list[str]:
    d = _limpar_doc(doc or "")
    if not d:
        return []
    out = [d]
    if len(d) == 11:
        out.append(d.zfill(14))
    return list(dict.fromkeys(out))


def _lookup_cliente_codigo_razao(empresa, cnpj_cpf_xml: str, razao_fallback: str) -> Tuple[str, str]:
    from cliente.models import Cliente

    codigo = "0"
    razao = _sanitizar_segmento_pasta(razao_fallback or "Tomador")
    for variant in _doc_match_variants(cnpj_cpf_xml):
        cli = (
            Cliente.objects.filter(empresa_id=empresa.pk, cnpj=variant).first()
            if getattr(empresa, "pk", None)
            else None
        )
        if cli:
            codigo = (getattr(cli, "codigo_externo", None) or "").strip() or "0"
            razao = _sanitizar_segmento_pasta(cli.razao or razao_fallback or "Tomador")
            break
    return codigo, razao


def _lookup_fornecedor_codigo_razao(empresa, cnpj_cpf_xml: str, razao_fallback: str) -> Tuple[str, str]:
    from fornecedor.models import Fornecedor
    from fornecedor.cnpj_utils import limpar_cnpj as limpar_forn

    codigo = "0"
    razao = _sanitizar_segmento_pasta(razao_fallback or "Prestador")
    doc_limpo = limpar_forn(cnpj_cpf_xml or "")
    if not doc_limpo or not getattr(empresa, "pk", None):
        return codigo, razao
    qs = Fornecedor.objects.filter(empresa_id=empresa.pk)
    for f in qs:
        if limpar_forn(f.cnpj or "") == doc_limpo:
            codigo = (getattr(f, "codigo_externo", None) or "").strip() or "0"
            razao = _sanitizar_segmento_pasta(f.razao or razao_fallback or "Prestador")
            return codigo, razao
    return codigo, razao


def _primeiro_infnfse_sped(root, nfutils) -> Any:
    ns = nfutils.NS_SPED
    tag_inf = nfutils._qname(ns, "infNFSe")
    inf_list = root.findall(".//%s" % tag_inf)
    if not inf_list:
        inf_one = root.find(tag_inf)
        if inf_one is not None:
            inf_list = [inf_one]
    return inf_list[0] if inf_list else None


def _extrair_metadados_sped(root, nfutils, empresa) -> Optional[dict[str, Any]]:
    if not nfutils._is_nfse_sped(root):
        return None
    inf = _primeiro_infnfse_sped(root, nfutils)
    if inf is None:
        return None
    _t, _d = nfutils._t, nfutils._d
    ns = nfutils.NS_SPED
    cnpj_prest = ""
    for path in (
        "emit/CNPJ",
        "emit/CPF",
        "DPS/infDPS/prest/CNPJ",
        "DPS/infDPS/prest/CPF",
        "prest/CNPJ",
    ):
        raw = _t(inf, path, ns)
        if raw:
            cnpj_prest = nfutils.limpar_cnpj(raw)
            break
    cnpj_toma = nfutils.limpar_cnpj(
        _t(inf, "DPS/infDPS/toma/CNPJ", ns) or _t(inf, "DPS/infDPS/toma/CPF", ns) or ""
    )
    nome_toma = _t(inf, "DPS/infDPS/toma/xNome", ns) or ""
    nome_prest = _t(inf, "emit/xNome", ns) or _t(inf, "DPS/infDPS/prest/xNome", ns) or ""
    d_compet = _d(inf, "DPS/infDPS/dCompet", ns)
    data_emi = _d(inf, "dhProc", ns) or _d(inf, "dhEmi", ns)
    ref_date = d_compet or data_emi or date.today()
    compet_pasta = f"{ref_date.month:02d}{ref_date.year}"
    emp_doc = nfutils.limpar_cnpj(empresa.cnpj or "")
    papel = None
    if cnpj_prest and emp_doc == cnpj_prest:
        papel = "prestador"
    elif cnpj_toma and emp_doc == cnpj_toma:
        papel = "tomador"
    elif cnpj_prest:
        papel = "prestador"
    elif cnpj_toma:
        papel = "tomador"
    return {
        "papel": papel,
        "cnpj_prestador": cnpj_prest,
        "cnpj_tomador": cnpj_toma,
        "nome_prestador": nome_prest,
        "nome_tomador": nome_toma,
        "compet_pasta": compet_pasta,
    }


def _escopo_abrasf(root, nfutils):
    if nfutils._local(root.tag) == "infnfse":
        return root
    if nfutils._local(root.tag) in ("compnfse", "nfse"):
        for child in root.iter():
            if nfutils._local(child.tag) == "infnfse":
                return child
    # Lote (ListaNfse, ConsultarNfseLote, etc.): primeiro InfNfse na árvore
    for child in root.iter():
        if nfutils._local(child.tag) == "infnfse":
            return child
    return root


def _extrair_prest_toma_abrasf(root, nfutils) -> Tuple[str, str, str, str]:
    """Retorna (cnpj_prest, nome_prest, cnpj_toma, nome_toma) com documentos só dígitos."""
    scope = _escopo_abrasf(root, nfutils)
    cnpj_prest, nome_prest = "", ""
    tomador_node = None
    for e in scope.iter():
        tag = nfutils._local(e.tag)
        if tag in ("tomadorservico", "tomador"):
            tomador_node = e
            break
    cnpj_toma, nome_toma = "", ""
    if tomador_node is not None:
        for raz in tomador_node.iter():
            if nfutils._local(raz.tag) == "razaosocial" and (raz.text or "").strip():
                nome_toma = raz.text.strip()
                break
        for idt in tomador_node.iter():
            if nfutils._local(idt.tag) in ("cnpj", "cpf") and (idt.text or "").strip():
                cnpj_toma = nfutils.limpar_cnpj(idt.text.strip())
                break
    prestador_node = None
    for e in scope.iter():
        if nfutils._local(e.tag) == "prestadorservico":
            prestador_node = e
            break
    if prestador_node is not None:
        for idp in prestador_node.iter():
            if nfutils._local(idp.tag) == "cnpj" and (idp.text or "").strip():
                cnpj_prest = nfutils.limpar_cnpj(idp.text.strip())
                break
        for idp in prestador_node.iter():
            if nfutils._local(idp.tag) == "razaosocial" and (idp.text or "").strip():
                nome_prest = idp.text.strip()
                break
    return cnpj_prest, nome_prest, cnpj_toma, nome_toma


def _data_emissao_abrasf(root, nfutils):
    scope = _escopo_abrasf(root, nfutils)
    for elem in scope.iter():
        lname = nfutils._local(elem.tag)
        text = (elem.text or "").strip()
        if not text:
            continue
        if lname in ("dataemissao", "dhemi"):
            try:
                from dateutil import parser as date_parser

                return date_parser.parse(text).date()
            except Exception:
                pass
    return None


def _extrair_numero_serie_xml(root, nfutils) -> Tuple[str, str]:
    """Número e série para nome de arquivo (SPED ou ABRASF)."""
    if nfutils._is_nfse_sped(root):
        inf = _primeiro_infnfse_sped(root, nfutils)
        if inf is not None:
            ns = nfutils.NS_SPED
            n = nfutils._t(inf, "nNFSe", ns) or "s_n"
            s = nfutils._t(inf, "DPS/infDPS/serie", ns) or "1"
            return str(n), str(s)
    scope = _escopo_abrasf(root, nfutils)
    n = nfutils.find_numero_nota_correct(scope) or "s_n"
    serie = "1"
    for elem in scope.iter():
        if nfutils._local(elem.tag) == "serie" and (elem.text or "").strip():
            serie = (elem.text or "").strip()
            break
    return str(n), serie


def validar_periodo_xml_nfse(xml_bytes: bytes, di: Optional[date], df: Optional[date]) -> Optional[str]:
    """
    Se di e df forem informados, exige que competência (dCompet) ou emissão do XML caia no intervalo [di, df].
    Retorna mensagem de erro ou None se OK / sem período.
    """
    if not di or not df:
        return None
    import xml.etree.ElementTree as ET

    from notasfiscais import utils as nfutils

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return "XML inválido para validar o período."
    refs: list[date] = []
    if nfutils._is_nfse_sped(root):
        inf = _primeiro_infnfse_sped(root, nfutils)
        if inf is not None:
            ns = nfutils.NS_SPED
            # Em integracoes reais o portal costuma exibir por data de emissao.
            # Aceita qualquer uma das datas estruturais no intervalo para evitar falso negativo.
            for p in ("dhEmi", "dhProc", "DPS/infDPS/dCompet"):
                d = nfutils._d(inf, p, ns)
                if d:
                    refs.append(d)
    if not refs:
        d = _data_emissao_abrasf(root, nfutils)
        if d:
            refs.append(d)
    if not refs:
        return "Não foi possível identificar competência ou emissão no XML para conferir o período."
    if any(di <= r <= df for r in refs):
        return None
    ref = refs[0]
    if ref < di or ref > df:
        refs_fmt = ", ".join(sorted({r.strftime("%d/%m/%Y") for r in refs}))
        return (
            f"A nota (datas encontradas: {refs_fmt}) está fora do período "
            f"{di.strftime('%d/%m/%Y')} a {df.strftime('%d/%m/%Y')}."
        )
    return None


def _write_copia_xml_e_pdf_opcional(
    dest_dir: Path,
    stem: str,
    xml_bytes: bytes,
    pdf_bytes: Optional[bytes],
    numero: str,
    serie: str,
) -> None:
    _garantir_pasta_copia_nfse(dest_dir)
    dest_xml = dest_dir / f"{stem}.xml"
    if dest_xml.is_file():
        dest_xml = dest_dir / f"{stem}_{numero}_{serie}.xml"
    dest_xml.write_bytes(xml_bytes)
    if pdf_bytes:
        dest_pdf = dest_dir / f"{stem}.pdf"
        if dest_pdf.is_file():
            dest_pdf = dest_dir / f"{stem}_{numero}_{serie}.pdf"
        dest_pdf.write_bytes(pdf_bytes)


def salvar_baixados_portal_nacional_files(
    xml_bytes: bytes,
    pdf_bytes: Optional[bytes],
    nome_stem: str,
    empresa,
    importar_canceladas: bool,
    *,
    html_bytes: Optional[bytes] = None,
) -> None:
    """
    Grava XML (e PDF se houver) nas pastas configuradas conforme papel no XML:
    emitida (empresa prestadora) → pasta prestador; recebida (tomadora) → pasta tomador.

    ``html_bytes``: página HTML da extensão/emitidas com a mesma nota — usado para detetar cancelamento
    quando o XML ainda não traz o evento.
    """
    try:
        import xml.etree.ElementTree as ET

        from notasfiscais import utils as nfutils

        root = ET.fromstring(xml_bytes)
        meta = _extrair_metadados_sped(root, nfutils, empresa) or _extrair_metadados_abrasf(root, nfutils, empresa)
        papel = meta.get("papel")
        if not papel and importar_canceladas:
            emp_doc = nfutils.limpar_cnpj(empresa.cnpj or "")
            raw_digits = re.sub(r"\D", "", xml_bytes.decode("utf-8", errors="replace")[:200000])
            if emp_doc and emp_doc in raw_digits:
                papel = "prestador"
                meta = dict(meta)
                meta["papel"] = "prestador"
                logger.info("Cópia portal: papel assumido «prestador» (CNPJ da empresa encontrado no XML; cancelada).")
        if not papel:
            logger.info("Cópia portal: papel (prestador/tomador) não determinado; não gravando em disco.")
            return
        base = _nfse_xml_base_prestador(empresa) if papel == "prestador" else _nfse_xml_base_tomador(empresa)
        if not base:
            return
        compet_pasta = _normalizar_pasta_mesano(meta.get("compet_pasta"), date.today())
        cancel_xml = xml_nfse_portal_indica_cancelada(xml_bytes)
        html_cancel = bool(html_bytes and html_extensao_portal_indica_nfse_cancelada(html_bytes))
        importar_efetivo = bool(importar_canceladas or cancel_xml or html_cancel)
        if papel == "prestador":
            codigo, razao = _lookup_cliente_codigo_razao(
                empresa,
                meta.get("cnpj_tomador") or "",
                meta.get("nome_tomador") or "Tomador",
            )
            segmento = f"{_sanitizar_segmento_pasta(codigo, 40)}-{_sanitizar_segmento_pasta(razao)}"
            if importar_efetivo:
                seg_emp = _segmento_pasta_empresa_codigo_razao(empresa)
                dest_dir = Path(base) / seg_emp / compet_pasta / "Cancelada"
            else:
                dest_dir = Path(base) / segmento / compet_pasta
        else:
            codigo, razao = _lookup_fornecedor_codigo_razao(
                empresa,
                meta.get("cnpj_prestador") or "",
                meta.get("nome_prestador") or "Prestador",
            )
            segmento = f"{_sanitizar_segmento_pasta(codigo, 40)}-{_sanitizar_segmento_pasta(razao)}"
            if importar_efetivo:
                seg_emp = _segmento_pasta_empresa_codigo_razao(empresa)
                dest_dir = Path(base) / seg_emp / compet_pasta / "Cancelada"
            else:
                dest_dir = Path(base) / segmento / compet_pasta
        stem = _sanitizar_segmento_pasta(nome_stem or "nfse", 80)
        num, ser = _extrair_numero_serie_xml(root, nfutils)
        if importar_efetivo:
            dest_xml = dest_dir / f"{stem}.xml"
            if dest_xml.is_file():
                logger.info(
                    "NFSe portal: cópia cancelada já existe (%s); não duplicar na pasta Cancelada.",
                    dest_xml,
                )
                return
        _write_copia_xml_e_pdf_opcional(dest_dir, stem, xml_bytes, pdf_bytes, num, ser)
        logger.info("NFSe portal: arquivos gravados em %s", dest_dir)
    except Exception as e:
        logger.warning("NFSe portal: não foi possível gravar cópia (%s)", e)


def _extrair_metadados_abrasf(root, nfutils, empresa) -> dict[str, Any]:
    cnpj_prest, nome_prest, cnpj_toma, nome_toma = _extrair_prest_toma_abrasf(root, nfutils)
    emp_doc = nfutils.limpar_cnpj(empresa.cnpj or "")
    papel = None
    if cnpj_prest and emp_doc == cnpj_prest:
        papel = "prestador"
    elif cnpj_toma and emp_doc == cnpj_toma:
        papel = "tomador"
    elif cnpj_prest:
        papel = "prestador"
    elif cnpj_toma:
        papel = "tomador"
    d = _data_emissao_abrasf(root, nfutils) or date.today()
    compet_pasta = f"{d.month:02d}{d.year}"
    return {
        "papel": papel,
        "cnpj_prestador": cnpj_prest,
        "cnpj_tomador": cnpj_toma,
        "nome_prestador": nome_prest,
        "nome_tomador": nome_toma,
        "compet_pasta": compet_pasta,
    }


def tentar_salvar_copia_xml_importacao(
    xml_bytes: bytes,
    nome_original: str,
    empresa,
    root,
    importar_canceladas: bool,
    resultado: dict[str, Any],
) -> None:
    """
    Grava cópia do XML se houver pasta configurada e ao menos uma nota importada neste arquivo.
    Erros de I/O são apenas logados (não interrompem a importação).
    """
    try:
        if not xml_bytes or not resultado or resultado.get("total_importadas", 0) <= 0:
            return
        nfses = resultado.get("nfses") or []
        first = nfses[0] if nfses else None
        if first is None:
            return

        from notasfiscais import utils as nfutils

        meta = _extrair_metadados_sped(root, nfutils, empresa)
        if meta is None:
            meta = _extrair_metadados_abrasf(root, nfutils, empresa)

        papel = meta.get("papel")
        if not papel:
            logger.info("NFSe XML cópia: papel (prestador/tomador) não determinado; não gravando.")
            return

        base = _nfse_xml_base_prestador(empresa) if papel == "prestador" else _nfse_xml_base_tomador(empresa)
        if not base:
            return

        ref_de = getattr(first, "data_emissao", None) or date.today()
        compet_pasta = _normalizar_pasta_mesano(meta.get("compet_pasta"), ref_de)
        cancel_xml = xml_nfse_portal_indica_cancelada(xml_bytes)
        importar_efetivo = bool(importar_canceladas or cancel_xml)

        if papel == "prestador":
            codigo, razao = _lookup_cliente_codigo_razao(empresa, first.cnpj_cpf or "", first.cliente or "")
            segmento = f"{_sanitizar_segmento_pasta(codigo, 40)}-{_sanitizar_segmento_pasta(razao)}"
            if importar_efetivo:
                seg_emp = _segmento_pasta_empresa_codigo_razao(empresa)
                dest_dir = Path(base) / seg_emp / compet_pasta / "Cancelada"
            else:
                dest_dir = Path(base) / segmento / compet_pasta
        else:
            codigo, razao = _lookup_fornecedor_codigo_razao(
                empresa,
                meta.get("cnpj_prestador") or "",
                meta.get("nome_prestador") or "",
            )
            segmento = f"{_sanitizar_segmento_pasta(codigo, 40)}-{_sanitizar_segmento_pasta(razao)}"
            if importar_efetivo:
                seg_emp = _segmento_pasta_empresa_codigo_razao(empresa)
                dest_dir = Path(base) / seg_emp / compet_pasta / "Cancelada"
            else:
                dest_dir = Path(base) / segmento / compet_pasta
        stem = Path(nome_original or "nfse.xml").stem or "nfse"
        stem = _sanitizar_segmento_pasta(stem, 80)
        nn = getattr(first, "numero_nota", None) or "s_n"
        ss = getattr(first, "serie", None) or "1"
        _write_copia_xml_e_pdf_opcional(dest_dir, stem, xml_bytes, None, str(nn), str(ss))
        logger.info("NFSe XML cópia gravada em %s", dest_dir / f"{stem}.xml")
    except Exception as e:
        logger.warning("NFSe XML cópia: não foi possível gravar (%s)", e)
