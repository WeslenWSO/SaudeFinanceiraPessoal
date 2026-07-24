"""
Importação em lote de XML/PDF do fluxo «Portal (extensão)» — usado pela view e pelo comando de automação.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from django.core.files.uploadedfile import SimpleUploadedFile

from .nfse_xml_copia import (
    emitidas_portal_manifest_chaves_canceladas,
    extrair_chave_acesso_nfse_html,
    extrair_chave_acesso_nfse_xml,
    html_extensao_portal_indica_nfse_cancelada,
    salvar_baixados_portal_nacional_files,
    validar_periodo_xml_nfse,
    xml_nfse_portal_indica_cancelada,
)
from .utils import import_nfse_from_xml

logger = logging.getLogger(__name__)


def _coletar_xml_pdf_um_nivel(
    pasta: Path, *, nome_prefixo: str, from_cancelada_subdir: bool
) -> list[tuple[str, bytes, Optional[bytes], bool]]:
    """Lê .xml num único nível; PDF pelo mesmo stem nesta mesma pasta."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    pdfs: dict[str, bytes] = {}
    for p in sorted(pasta.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() == ".pdf":
            try:
                pdfs[p.stem.lower()] = p.read_bytes()
            except OSError as e:
                logger.warning("Não leu PDF %s: %s", p, e)
    out: list[tuple[str, bytes, Optional[bytes], bool]] = []
    for p in sorted(pasta.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".xml":
            continue
        try:
            xml_b = p.read_bytes()
        except OSError as e:
            logger.warning("Não leu XML %s: %s", p, e)
            continue
        stem = p.stem.lower()
        logical = f"{nome_prefixo}{p.name}" if nome_prefixo else p.name
        out.append((logical, xml_b, pdfs.get(stem), from_cancelada_subdir))
    return out


def coletar_xml_pdf_de_diretorio(
    pasta: Path, *, incluir_subpasta_cancelada: bool = True
) -> list[tuple[str, bytes, Optional[bytes], bool]]:
    """
    Lê os .xml da pasta principal e, se existir, da subpasta ``Cancelada/`` (um nível em cada).

    Retorna ``(nome_lógico, xml_bytes, pdf_bytes|None, from_cancelada_subdir)``.
    Itens com ``from_cancelada_subdir=True`` (subpasta ``Cancelada/``) são importados como canceladas (valores zerados).
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    out = _coletar_xml_pdf_um_nivel(pasta, nome_prefixo="", from_cancelada_subdir=False)
    if incluir_subpasta_cancelada:
        sub = pasta / "Cancelada"
        if sub.is_dir():
            out.extend(
                _coletar_xml_pdf_um_nivel(
                    sub, nome_prefixo="Cancelada/", from_cancelada_subdir=True
                )
            )
    return out


def _stem_chave44_nome_arquivo(path: Path) -> Optional[str]:
    """Chave de 44 dígitos extraída do nome do ficheiro (ex.: duplicados Chrome ``… (1).pdf``)."""
    stem = path.stem.strip()
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem).strip()
    if re.fullmatch(r"\d{44}", stem):
        return stem
    return None


def organizar_arquivos_cancelados_na_inbox_portal(
    pasta_mes: Path,
    *,
    on_log: Optional[Callable[[str], None]] = None,
) -> int:
    """
    Cria ``Cancelada/`` na pasta do mês (inbox do portal) e move para lá ficheiros cuja chave (44 dígitos
    no nome) consta no manifesto ``._nfse_emitidas_portal.json`` como cancelada, ou ``.xml`` na raiz cujo
    conteúdo indica cancelamento, ou ``.html``/``.htm`` da extensão com tags de situação cancelada.
    Inclui pares ``.pdf`` / ``.html`` com o mesmo stem da chave.
    """
    log = on_log or (lambda m: logger.info("%s", m))
    pasta_mes = Path(pasta_mes)
    if not pasta_mes.is_dir():
        return 0

    cdir = pasta_mes / "Cancelada"
    chaves_manifest = emitidas_portal_manifest_chaves_canceladas(pasta_mes)
    movidos = 0

    def _mover(p: Path) -> None:
        nonlocal movidos
        try:
            cdir.mkdir(parents=True, exist_ok=True)
            dest = cdir / p.name
            if dest.resolve() == p.resolve():
                return
            if dest.exists():
                log(f"Cancelada/: {dest.name} já existe; não mover duplicado.")
                return
            shutil.move(os.fspath(p), os.fspath(dest))
            movidos += 1
            log(f"Cancelada/: movido {p.name}")
        except OSError as e:
            log(f"Cancelada/: erro ao mover {p.name} — {e}")

    exts_manifest = {".xml", ".pdf", ".html", ".htm"}
    for p in sorted(pasta_mes.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        if p.name.startswith("._nfse_emitidas_portal"):
            continue
        if p.suffix.lower() not in exts_manifest:
            continue
        ch = _stem_chave44_nome_arquivo(p)
        if ch and ch in chaves_manifest:
            _mover(p)

    for p in sorted(set(list(pasta_mes.glob("*.xml")) + list(pasta_mes.glob("*.XML")))):
        if not p.is_file() or p.parent.resolve() != pasta_mes.resolve():
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if not xml_nfse_portal_indica_cancelada(raw):
            continue
        _mover(p)
        chave_nf = extrair_chave_acesso_nfse_xml(raw) or _stem_chave44_nome_arquivo(p)
        if chave_nf:
            for buddy in list(pasta_mes.iterdir()):
                if not buddy.is_file() or buddy.suffix.lower() not in (".pdf", ".html", ".htm"):
                    continue
                if buddy.parent.resolve() != pasta_mes.resolve():
                    continue
                if _stem_chave44_nome_arquivo(buddy) == chave_nf:
                    _mover(buddy)

    for p in sorted(pasta_mes.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.suffix.lower() not in (".html", ".htm"):
            continue
        if p.parent.resolve() != pasta_mes.resolve():
            continue
        try:
            hb = p.read_bytes()
        except OSError:
            continue
        if not html_extensao_portal_indica_nfse_cancelada(hb):
            continue
        ch_html = extrair_chave_acesso_nfse_html(hb) or _stem_chave44_nome_arquivo(p)
        _mover(p)
        if ch_html:
            for buddy in list(pasta_mes.iterdir()):
                if not buddy.is_file() or buddy.suffix.lower() not in (".xml", ".pdf"):
                    continue
                if buddy.parent.resolve() != pasta_mes.resolve():
                    continue
                if _stem_chave44_nome_arquivo(buddy) == ch_html:
                    _mover(buddy)

    if movidos and not chaves_manifest:
        log(f"Cancelada/: {movidos} ficheiro(s) movidos (deteção por conteúdo XML).")
    elif movidos:
        log(f"Cancelada/: {movidos} ficheiro(s) movidos (manifesto e/ou XML).")
    return movidos


def processar_portal_extensao_arquivos(
    empresa,
    user,
    data_inicio: date,
    data_fim: date,
    itens: list[tuple[str, bytes, Optional[bytes], bool]]
    | list[tuple[str, bytes, Optional[bytes]]],
    importar_canceladas: bool = False,
    *,
    on_warning: Optional[Callable[[str], None]] = None,
    pasta_manifest: Optional[Path] = None,
) -> dict[str, Any]:
    """
    itens: tuplas ``(nome_xml, xml_bytes, pdf_bytes_opcional)`` ou com quarto elemento booleano
    ``from_cancelada_subdir`` — quando True, importa como cancelada (valores zerados).

    O parâmetro ``importar_canceladas`` é ignorado (mantido só por compatibilidade com chamadas antigas).
    Notas canceladas: apenas ficheiros em ``Cancelada/``, chaves no manifesto do Selenium, ou XML/HTML
    que indiquem cancelamento.

    ``pasta_manifest``: pasta onde o Selenium gravou ``._nfse_emitidas_portal.json`` (``data-situacao``
    do portal, ex. ``P104_NFSE_CANCELADA``) para gravar/importar como cancelada mesmo sem sinal no XML.
    """
    warn = on_warning or (lambda m: None)
    if importar_canceladas:
        logger.info(
            "processar_portal_extensao_arquivos: parâmetro importar_canceladas=True ignorado; "
            "canceladas só por subpasta Cancelada/, manifesto do portal ou conteúdo XML/HTML."
        )

    chaves_cancel_manifest: set[str] = set()
    if pasta_manifest is not None:
        chaves_cancel_manifest = emitidas_portal_manifest_chaves_canceladas(pasta_manifest)
        if chaves_cancel_manifest:
            try:
                (Path(pasta_manifest) / "Cancelada").mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning("Não foi possível criar subpasta Cancelada na inbox: %s", e)

    total_imp = 0
    total_ign = 0
    total_erros = 0
    erros_periodo: list[str] = []

    for row in itens:
        if len(row) == 4:
            nome_xml, xml_bytes, pdf_bytes, from_cancelada_subdir = row
        else:
            nome_xml, xml_bytes, pdf_bytes = row  # type: ignore[misc]
            from_cancelada_subdir = False
        nome_norm = (nome_xml or "").replace("\\", "/")
        if not from_cancelada_subdir and (
            nome_norm.lower().startswith("cancelada/")
            or "/cancelada/" in nome_norm.lower()
        ):
            from_cancelada_subdir = True
        chave_nf = extrair_chave_acesso_nfse_xml(xml_bytes)
        if not chave_nf:
            stem_arq = Path(os.path.basename(nome_xml)).stem
            if re.fullmatch(r"\d{44}", stem_arq):
                chave_nf = stem_arq
        cancel_por_manifest_emitidas = bool(chave_nf and chave_nf in chaves_cancel_manifest)
        html_b: Optional[bytes] = None
        if pasta_manifest is not None:
            pm = Path(pasta_manifest)
            base_stem = Path(os.path.basename(nome_xml)).stem
            for ext in (".html", ".htm"):
                hp = pm / f"{base_stem}{ext}"
                if hp.is_file():
                    try:
                        html_b = hp.read_bytes()
                    except OSError:
                        html_b = None
                    break
            if not html_b and chave_nf:
                for ext in (".html", ".htm"):
                    hp = pm / f"{chave_nf}{ext}"
                    if hp.is_file():
                        try:
                            html_b = hp.read_bytes()
                        except OSError:
                            html_b = None
                        break
        cancel_html = bool(html_b and html_extensao_portal_indica_nfse_cancelada(html_b))
        cancel_efetivo = bool(
            from_cancelada_subdir
            or xml_nfse_portal_indica_cancelada(xml_bytes)
            or cancel_por_manifest_emitidas
            or cancel_html
        )

        msg_periodo = validar_periodo_xml_nfse(xml_bytes, data_inicio, data_fim)
        if msg_periodo:
            erros_periodo.append(f"{nome_xml}: {msg_periodo}")
            total_erros += 1
            continue

        stem = os.path.splitext(os.path.basename(nome_xml))[0] or "nfse"
        salvar_baixados_portal_nacional_files(
            xml_bytes,
            pdf_bytes,
            stem,
            empresa,
            importar_canceladas=cancel_efetivo,
            html_bytes=html_b,
        )

        if cancel_efetivo and pasta_manifest is not None:
            try:
                cdir = Path(pasta_manifest) / "Cancelada"
                cdir.mkdir(parents=True, exist_ok=True)
                nome_base = os.path.basename(nome_xml) or "nfse.xml"
                (cdir / nome_base).write_bytes(xml_bytes)
                if pdf_bytes:
                    pdf_name = os.path.splitext(nome_base)[0] + ".pdf"
                    (cdir / pdf_name).write_bytes(pdf_bytes)
                if html_b:
                    h_name = os.path.splitext(nome_base)[0] + ".html"
                    (cdir / h_name).write_bytes(html_b)
            except OSError as e:
                warn(f"{os.path.basename(nome_xml)}: não foi possível copiar para Cancelada/ na inbox — {e}")

        rel = nome_norm or "nfse.xml"
        if from_cancelada_subdir:
            if rel.lower().startswith("cancelada/"):
                upload_name = rel
            else:
                upload_name = f"Cancelada/{os.path.basename(rel) or 'nfse.xml'}"
        else:
            upload_name = os.path.basename(rel) or "nfse.xml"
        uploaded = SimpleUploadedFile(upload_name, xml_bytes, content_type="application/xml")
        try:
            resultado = import_nfse_from_xml(
                uploaded,
                user,
                empresa,
                importar_canceladas=cancel_efetivo,
            )
        except ValueError as e:
            total_erros += 1
            warn(f"{upload_name}: {e}")
            continue
        except Exception as e:
            total_erros += 1
            warn(f"{upload_name}: erro na importação — {e}")
            continue

        total_imp += int(resultado.get("total_importadas") or 0)
        total_ign += int(resultado.get("total_ignoradas") or 0)

    for ep in erros_periodo[:20]:
        warn(ep)
    if len(erros_periodo) > 20:
        warn(f"... e mais {len(erros_periodo) - 20} arquivo(s) fora do período.")

    return {
        "total_importadas": total_imp,
        "total_ignoradas": total_ign,
        "total_erros": total_erros,
        "erros_periodo_count": len(erros_periodo),
    }
