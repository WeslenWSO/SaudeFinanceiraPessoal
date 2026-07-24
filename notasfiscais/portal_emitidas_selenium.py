"""
Automação do Emissor Nacional (login + Notas emitidas + XML/PDF) com Selenium.

Usa a mesma configuração ``NFSE_PORTAL_PLAYWRIGHT`` em ``settings`` (URLs, seletores, perfil em disco).
Dependência: ``pip install selenium`` (4.6+ inclui gestão do ChromeDriver). Requer **Chrome ou Edge** instalado.

Com **perfil persistente** (``persistent_context``/``--perfil``), usa ``user-data-dir`` dedicado (extensões/cookies).
Sem perfil: perfil temporário em disco (sessão limpa a cada execução).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse, urljoin

from django.conf import settings as django_settings

from notasfiscais.nfse_xml_copia import (
    emitidas_portal_manifest_append,
    emitidas_portal_manifest_chave44_ja_baixada,
    emitidas_portal_manifest_limpar,
    emitidas_portal_manifest_web_chave_ja_listada,
    extrair_chave_acesso_nfse_xml,
    portal_emitidas_data_situacao_indica_cancelada,
    xml_nfse_portal_indica_cancelada,
)

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _cfg() -> dict[str, Any]:
    d = getattr(django_settings, "NFSE_PORTAL_PLAYWRIGHT", None) or {}
    if not isinstance(d, dict):
        return {}
    return d


def _aguardar_pasta_sem_crdownload(
    pasta: Path,
    seg_max: float,
    log: Callable[[str], None],
    intervalo: float = 0.45,
) -> None:
    """
    Espera o Chrome terminar downloads na pasta (ficheiros .crdownload desaparecem ao concluir).
    Se não houver pendentes, retorna quase de imediato.
    """
    p = Path(pasta)
    if not p.is_dir():
        return
    t0 = time.monotonic()
    while time.monotonic() - t0 < seg_max:
        if not list(p.glob("*.crdownload")):
            time.sleep(0.35)
            if not list(p.glob("*.crdownload")):
                return
        time.sleep(intervalo)
    log(
        f"Aviso: atingido o tempo máximo ({seg_max:.0f}s) à espera de downloads — "
        "verifique se ficou algum .crdownload na pasta."
    )


def diagnostico_selenium_carregavel() -> tuple[bool, str]:
    """Verifica se ``selenium`` e um WebDriver conseguem arrancar neste interpretador."""
    import sys

    exe = sys.executable
    try:
        from selenium import webdriver as _wd  # noqa: F401
        from selenium.webdriver.chrome.options import Options as _ChromeO  # noqa: F401
    except ModuleNotFoundError as e:
        return False, (
            "O pacote «selenium» não está instalado neste Python.\n\n"
            f"Detalhe: {e}\n\n"
            f"Interpretador: {exe}\n\n"
            "No mesmo ambiente do «runserver», execute:\n"
            "  pip install selenium"
        )
    except ImportError as e:
        return False, f"Erro ao importar Selenium: {e}\n\nInterpretador: {exe}"
    return True, ""


def _persistent_profile(cfg: dict[str, Any], log: Callable[[str], None]) -> tuple[bool, Path | None, str]:
    raw = cfg.get("persistent_context")
    if raw is True:
        use = True
    elif raw is False:
        use = False
    elif isinstance(raw, str) and raw.strip().lower() in ("1", "true", "yes", "on"):
        use = True
    else:
        use = False
    if os.environ.get("NFSE_PLAYWRIGHT_PERFIL", "").strip().lower() in ("1", "true", "yes"):
        use = True
    if os.environ.get("NFSE_PLAYWRIGHT_SEM_PERFIL", "").strip().lower() in ("1", "true", "yes"):
        use = False

    ch_cfg = (cfg.get("browser_channel") or "").strip() or None

    if not use:
        return False, None, ch_cfg

    pdir = (cfg.get("persistent_user_data_dir") or "").strip()
    if not pdir:
        pdir = str(Path.home() / ".saude_financeira" / "playwright_nfse_profile")
    user_data = Path(pdir).expanduser().resolve()

    ch = (ch_cfg or "chrome").strip().lower()
    if ch not in ("chrome", "msedge"):
        log(
            f"Perfil persistente exige browser_channel «chrome» ou «msedge» (recebido: {ch!r}); "
            "usando Chrome sem pasta fixa de perfil."
        )
        return False, None, ch_cfg

    return True, user_data, ch


def _screenshot_erro(driver, out_dir: Path, nome: str, log: Callable[[str], None]) -> None:
    if driver is None:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        shot = out_dir / nome
        driver.save_screenshot(str(shot))
        log(f"Screenshot (erro): {shot}")
    except Exception as ex:
        log(f"Aviso: não gravou screenshot ({ex})")


def _wait(driver, timeout: float):
    return WebDriverWait(driver, timeout)


def _emitidas_url_base(cfg: dict[str, Any]) -> str:
    u = (cfg.get("emitidas_page_url") or "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas").strip()
    return u.split("?", 1)[0].rstrip("/")


def _navegar_emitidas_com_periodo(
    driver,
    wait,
    data_inicio: date,
    data_fim: date,
    after_emit_url: str,
    cfg: dict[str, Any],
    timeout_sec: float,
    log: Callable[[str], None],
) -> bool:
    from urllib.parse import urlencode

    di_br = data_inicio.strftime("%d/%m/%Y")
    df_br = data_fim.strftime("%d/%m/%Y")
    if (data_fim - data_inicio).days > 31:
        log("Aviso: o portal costuma limitar o filtro a ~30 dias; reduza o período se o resultado vier vazio.")
    if after_emit_url:
        try:
            log("Abrindo after_login_emitidas_url …")
            driver.set_page_load_timeout(timeout_sec)
            driver.get(after_emit_url)
            time.sleep(2)
            return True
        except Exception as ex:
            log(f"Aviso: after_login_emitidas_url falhou ({ex}); tentando URL padrão com período.")
    base = _emitidas_url_base(cfg)
    qs = urlencode({"datainicio": di_br, "datafim": df_br})
    url = f"{base}?{qs}"
    try:
        log(f"Abrindo lista de emitidas com período: {url}")
        driver.set_page_load_timeout(timeout_sec)
        driver.get(url)
        time.sleep(2.5)
        return True
    except Exception as ex:
        log(f"Aviso: goto emitidas falhou ({ex}).")
        return False


def _tentar_preencher_login(
    driver,
    wait,
    login: str,
    log: Callable[[str], None],
    user_selectors: list[str],
    timeout_sec: float,
) -> bool:
    for sel in user_selectors:
        if not (sel or "").strip():
            continue
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel.strip())
            for el in els:
                if el.is_displayed():
                    el.clear()
                    el.send_keys(login)
                    log(f"Login preenchido (user_selectors: {sel!r}).")
                    return True
        except Exception:
            continue

    for sel in (
        'input[formcontrolname="login"]',
        'input[formcontrolname="usuario"]',
        'input[formcontrolname="cpfCnpj"]',
        "input#usuario",
        "input#login",
        'input[name="usuario"]',
        'input[name="login"]',
        'input[id*="usuario"]',
        'input[id*="login"]',
        'input[id*="cpf"]',
        'input[id*="cnpj"]',
        "input[type=email]",
    ):
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    el.clear()
                    el.send_keys(login)
                    log(f"Login preenchido (seletor {sel!r}).")
                    return True
        except Exception:
            continue

    for xp in (
        "//label[contains(translate(., 'ÁÂÃÀáâãà', 'aaaaaa'), 'usu') or contains(., 'CPF') or contains(., 'CNPJ')]/following::input[1]",
        "//input[contains(@placeholder,'CPF') or contains(@placeholder,'CNPJ') or contains(@placeholder,'usu')]",
    ):
        try:
            els = driver.find_elements(By.XPATH, xp)
            for el in els:
                if el.is_displayed():
                    el.clear()
                    el.send_keys(login)
                    log("Login preenchido (XPath heurístico).")
                    return True
        except Exception:
            continue

    try:
        for sel in ('input[type="text"]', "input:not([type])"):
            for el in driver.find_elements(By.CSS_SELECTOR, sel)[:12]:
                try:
                    if not el.is_displayed():
                        continue
                    if el.size.get("width", 0) < 80:
                        continue
                    el.clear()
                    el.send_keys(login)
                    log(f"Login preenchido (heurística {sel!r}).")
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    return False


def _fill_password(driver, password_selector: str, senha: str, log: Callable[[str], None]) -> bool:
    pwd_attempts: list[str] = []
    if password_selector:
        pwd_attempts.append(password_selector.strip())
    pwd_attempts.extend(['input[type="password"]'])
    seen: set[str] = set()
    for sel in pwd_attempts:
        if not sel or sel in seen:
            continue
        seen.add(sel)
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    el.clear()
                    el.send_keys(senha)
                    log(f"Senha preenchida ({sel!r}).")
                    return True
        except Exception:
            continue
    return False


def _playwright_selector_to_xpath(sel: str) -> str | None:
    sel = sel.strip()
    m = re.match(r'button:has-text\("([^"]+)"\)', sel, re.I)
    if m:
        t = m.group(1)
        return f"//button[contains(., {repr(t)})]"
    if sel.startswith("//"):
        return sel
    return None


def _click_submit_login(
    driver,
    wait,
    submit_selectors: list[str],
    timeout_sec: float,
    log: Callable[[str], None],
) -> bool:
    for sel in submit_selectors:
        if not sel or str(sel).strip().startswith("role="):
            continue
        s = str(sel).strip()
        xp = _playwright_selector_to_xpath(s)
        locators: list[tuple[str, str]] = []
        if xp:
            locators.append((By.XPATH, xp))
        else:
            locators.append((By.CSS_SELECTOR, s))
        for by, val in locators:
            try:
                el = wait.until(EC.element_to_be_clickable((by, val)))
                if el.is_displayed():
                    el.click()
                    log(f"Clique em enviar ({s}).")
                    return True
            except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
                continue
    for name in ("Entrar", "Acessar", "Continuar", "Avançar"):
        xp = f"//button[contains(., {repr(name)})]"
        try:
            el = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            log(f"Clique em botão ({name}).")
            return True
        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
            continue
    return False


def _emitidas_fallback_menu_principal(
    driver,
    wait,
    emitidas_texts: list[str],
    after_emit_url: str,
    timeout_sec: float,
    log: Callable[[str], None],
) -> bool:
    if after_emit_url:
        return False
    for label in emitidas_texts:
        if len((label or "").strip()) < 2:
            continue
        try:
            xp = f"//a[contains(., {repr(label.strip())})]"
            els = driver.find_elements(By.XPATH, xp)
            for el in els:
                if el.is_displayed():
                    el.click()
                    log(f"Clique em link: {label!r}")
                    time.sleep(1.5)
                    return True
        except Exception:
            pass
    for href_part in ("emitid", "emitida", "Notas/Emitidas"):
        try:
            el = driver.find_element(By.CSS_SELECTOR, f'a[href*="{href_part}"]')
            if el.is_displayed():
                el.click()
                log(f"Clique em link href*={href_part!r}")
                time.sleep(1.5)
                return True
        except Exception:
            continue
    return False


def _emitidas_preencher_campos_e_filtrar(
    driver,
    wait,
    data_inicio: date,
    data_fim: date,
    timeout_sec: float,
    log: Callable[[str], None],
) -> None:
    di_br = data_inicio.strftime("%d/%m/%Y")
    df_br = data_fim.strftime("%d/%m/%Y")
    di_iso = data_inicio.isoformat()
    df_iso = data_fim.isoformat()

    for lab_pat in (r"data\s*inicial", r"^\s*Data\s+Inicial\s*$"):
        try:
            labs = driver.find_elements(By.XPATH, "//label")
            for lab in labs:
                if not lab.is_displayed():
                    continue
                if re.search(lab_pat, (lab.text or ""), re.I):
                    fid = lab.get_attribute("for")
                    if fid:
                        inp = driver.find_elements(By.ID, fid)
                        if inp and inp[0].is_displayed():
                            inp[0].clear()
                            inp[0].send_keys(di_br)
                            log(f"Data inicial preenchida ({lab_pat}).")
                            break
        except Exception:
            continue

    for lab_pat in (r"data\s*final", r"^\s*Data\s+Final\s*$"):
        try:
            labs = driver.find_elements(By.XPATH, "//label")
            for lab in labs:
                if not lab.is_displayed():
                    continue
                if re.search(lab_pat, (lab.text or ""), re.I):
                    fid = lab.get_attribute("for")
                    if fid:
                        inp = driver.find_elements(By.ID, fid)
                        if inp and inp[0].is_displayed():
                            inp[0].clear()
                            inp[0].send_keys(df_br)
                            log(f"Data final preenchida ({lab_pat}).")
                            break
        except Exception:
            continue

    try:
        dates = driver.find_elements(By.CSS_SELECTOR, 'input[type="date"]')
        if len(dates) >= 2:
            if dates[0].is_displayed():
                dates[0].clear()
                dates[0].send_keys(di_iso)
            if dates[1].is_displayed():
                dates[1].clear()
                dates[1].send_keys(df_iso)
            log("Campos type=date preenchidos (ISO).")
        elif len(dates) == 1 and dates[0].is_displayed():
            dates[0].clear()
            dates[0].send_keys(di_iso)
    except Exception as ex:
        log(f"Aviso: inputs type=date ({ex}).")

    try:
        phs = driver.find_elements(
            By.XPATH,
            "//input[contains(@placeholder,'dd/mm') or contains(@placeholder,'__')]",
        )
        if len(phs) >= 2:
            phs[0].clear()
            phs[0].send_keys(di_br)
            phs[1].clear()
            phs[1].send_keys(df_br)
            log("Datas preenchidas por placeholder.")
    except Exception:
        pass

    try:
        btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(translate(., 'FILTRAR', 'filtrar'), 'filtrar')]")
            )
        )
        btn.click()
        log("Clique em Filtrar.")
        time.sleep(2.5)
    except Exception as ex:
        log(f"Aviso: botão Filtrar não encontrado ou falhou ({ex}).")


def _overlay_root(driver):
    return driver.find_elements(
        By.CSS_SELECTOR,
        ".cdk-overlay-container .mat-mdc-menu-panel, .cdk-overlay-container mat-menu-panel, "
        ".cdk-overlay-container [role='menu']",
    )


def _emitidas_clicar_download_menu(
    driver,
    label_pattern: str,
    log: Callable[[str], None],
    row_el=None,
) -> bool:
    pat = re.compile(label_pattern, re.I)

    def _try_click_elements(els) -> bool:
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                t = (el.text or "") + (el.get_attribute("innerText") or "")
                if not pat.search(t):
                    continue
                el.click()
                log(f"Menu: clique em «{label_pattern}».")
                time.sleep(1.2)
                return True
            except Exception:
                continue
        return False

    if row_el is not None:
        try:
            for css in (
                "td.td-opcoes a",
                "td.td-opcoes button",
                ".menu-suspenso-tabela a",
                ".menu-suspenso-tabela button",
                ".dropdown-menu a",
                ".dropdown-menu button",
            ):
                if _try_click_elements(row_el.find_elements(By.CSS_SELECTOR, css)):
                    return True
        except Exception:
            pass

    for el in _overlay_root(driver):
        try:
            for sub in el.find_elements(By.CSS_SELECTOR, "button, a[role='menuitem'], [role='menuitem']"):
                if _try_click_elements([sub]):
                    return True
        except Exception:
            pass

    try:
        for el in driver.find_elements(By.CSS_SELECTOR, ".dropdown-menu.show a, .dropdown-menu.show button"):
            if _try_click_elements([el]):
                return True
    except Exception:
        pass

    try:
        for el in driver.find_elements(By.CSS_SELECTOR, "[role='menuitem'], a, button"):
            if not el.is_displayed():
                continue
            t = (el.text or "") + (el.get_attribute("innerText") or "")
            if pat.search(t):
                el.click()
                log(f"Menu: clique em «{label_pattern}» (fallback).")
                time.sleep(1.2)
                return True
    except Exception:
        pass
    return False


def _emitidas_coletar_linhas(driver, log: Callable[[str], None]):
    specs: list[tuple[str, str | None]] = [
        ("table.table-striped tbody tr", "td.td-opcoes"),
        ("table.table-striped tbody tr", "td"),
        ("mat-table mat-row", "mat-cell"),
        ("tbody[role='rowgroup'] tr", "td"),
        ("table tbody tr", "td"),
        ("[role='grid'] [role='row']", "[role='gridcell']"),
    ]
    for sel, cell in specs:
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, sel)
            out = []
            for r in rows:
                try:
                    if cell:
                        if not r.find_elements(By.CSS_SELECTOR, cell):
                            continue
                    out.append(r)
                except StaleElementReferenceException:
                    continue
            if out:
                log(f"Tabela de notas: «{sel}»" + (f" com «{cell}»" if cell else "") + f" ({len(out)} linha(s)).")
                return out
        except Exception:
            continue
    return []


def _emitidas_resolver_tr(row):
    try:
        if row.tag_name.lower() == "tr":
            return row
        return row.find_element(By.XPATH, "./ancestor::tr[1]")
    except Exception:
        return row


def _emitidas_data_situacao_tr(row) -> str:
    try:
        return (_emitidas_resolver_tr(row).get_attribute("data-situacao") or "").strip()
    except Exception:
        return ""


def _emitidas_html_celula_situacao_tr(row) -> str:
    """
    HTML só da coluna de situação. O ``outerHTML`` da linha inclui menus («Cancelar», etc.) e gera falsos positivos.
    """
    try:
        tr = _emitidas_resolver_tr(row)
    except Exception:
        return ""
    selectors = (
        "td.td-situacao",
        "td[class*='td-situacao']",
        "td[class*='situacao']",
        "[class*='mat-column-situacao']",
        "[class*='mat-column-situacaoNFe']",
        "td.cdk-column-situacao",
        "[class*='cdk-column-situacao']",
    )
    for sel in selectors:
        try:
            for el in tr.find_elements(By.CSS_SELECTOR, sel):
                try:
                    h = el.get_attribute("innerHTML") or ""
                except Exception:
                    continue
                if h.strip():
                    return h
        except Exception:
            continue
    return ""


def _emitidas_linha_portal_nfse_cancelada(row) -> tuple[bool, str]:
    """
    Cancelada na grelha «Emitidas»: ``data-situacao`` (ex. P104_NFSE_CANCELADA) ou sinais só na célula de situação
    (ícone ``tb-cancelada.svg``, etc.) — nunca o HTML da linha inteira (menus «Cancelar»).
    """
    situ = _emitidas_data_situacao_tr(row)
    if portal_emitidas_data_situacao_indica_cancelada(situ):
        return True, situ
    cell = _emitidas_html_celula_situacao_tr(row)
    if not (cell or "").strip():
        return False, situ
    low = cell.lower()
    compact = re.sub(r"\s+", "", low)
    if "p104_nfse_cancelada" in compact:
        return True, situ or "P104_NFSE_CANCELADA"
    if "tb-cancelada.svg" in low:
        return True, situ or "tb-cancelada.svg"
    if "data-original-title" in low and "cancel" in low and ("nfse" in low or "nfs-e" in low):
        return True, situ or "data-original-title"
    return False, situ


def _emitidas_mover_baixados_para_cancelada(
    download_dir: Path | None,
    cancel_portal: bool,
    novo_xml: Path | None,
    pdf_paths_antes: set[str],
    log: Callable[[str], None],
    prefix: str,
) -> None:
    """Cria ``Cancelada/`` na pasta de downloads e move para lá XML (e PDFs novos) quando a linha é cancelada."""
    if not download_dir or not cancel_portal:
        return
    root = Path(download_dir).resolve()
    dest = Path(download_dir) / "Cancelada"
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log(f"{prefix}: não criou Cancelada/ — {e}")
        return
    dest_r = dest.resolve()

    if novo_xml and novo_xml.is_file():
        try:
            xp = novo_xml.resolve()
            if xp.parent == root and not str(xp).startswith(str(dest_r)):
                shutil.move(str(novo_xml), str(dest / novo_xml.name))
                log(f"{prefix}: XML em Cancelada/ ({novo_xml.name}).")
        except OSError as e:
            log(f"{prefix}: não moveu XML para Cancelada/ — {e}")

    try:
        for p in Path(download_dir).glob("*.pdf"):
            if not p.is_file():
                continue
            sp = str(p.resolve())
            if sp in pdf_paths_antes:
                continue
            try:
                if p.resolve().parent != root:
                    continue
            except OSError:
                continue
            try:
                shutil.move(str(p), str(dest / p.name))
                log(f"{prefix}: PDF em Cancelada/ ({p.name}).")
            except OSError as e:
                log(f"{prefix}: não moveu PDF para Cancelada/ — {e}")
    except Exception as e:
        log(f"{prefix}: aviso ao mover PDFs — {e}")


def _emitidas_web_chave_tr(row) -> str:
    try:
        return (_emitidas_resolver_tr(row).get_attribute("data-chave") or "").strip()
    except Exception:
        return ""


def _emitidas_aguardar_novo_xml(
    download_dir: Path, paths_antes: set[str], log: Callable[[str], None], timeout: float = 48.0
) -> Path | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for p in sorted(download_dir.glob("*.xml"), key=lambda q: q.stat().st_mtime, reverse=True):
                sp = str(p.resolve())
                if sp in paths_antes:
                    continue
                try:
                    if p.stat().st_size < 80:
                        time.sleep(0.35)
                        continue
                except OSError:
                    continue
                return p
        except Exception:
            pass
        time.sleep(0.45)
    log("Aviso: timeout a aguardar novo ficheiro .xml após «Download XML».")
    return None


def _chave44_na_linha(row) -> str | None:
    try:
        blob = (row.get_attribute("innerHTML") or "") + " " + (row.get_attribute("outerHTML") or "")
        blob = re.sub(r"\s+", "", blob)
    except Exception:
        return None
    m = re.search(r"(?<![0-9])(\d{44})(?![0-9])", blob)
    return m.group(1) if m else None


def _emitidas_xml_ja_baixado(download_dir: Path | None, chave: str) -> bool:
    if not download_dir or not chave:
        return False
    d = Path(download_dir)
    for name in (f"{chave}.xml", f"{chave}.XML"):
        for folder in (d, d / "Cancelada"):
            p = folder / name
            if p.is_file():
                return True
    return False


def _emitidas_max_pagina_barra(driver) -> int:
    """Maior número de página visível na barra (links ``pg=`` ou texto numérico). Mínimo 1."""
    m = 1
    for a in driver.find_elements(
        By.CSS_SELECTOR,
        "ul.pagination a[href*='pg='], ul[class*='pagination'] a[href*='pg='], nav ul.pagination a[href*='pg=']",
    ):
        try:
            href = (a.get_attribute("href") or "").strip()
            if "pg=" not in href.lower():
                continue
            pq = parse_qs(urlparse(href).query)
            if "pg" not in pq or not str(pq["pg"][0]).strip().isdigit():
                continue
            m = max(m, int(str(pq["pg"][0]).strip()))
        except Exception:
            continue
    for a in driver.find_elements(By.CSS_SELECTOR, "ul.pagination a, ul[class*='pagination'] a"):
        t = (a.text or "").strip()
        if t.isdigit():
            m = max(m, int(t))
    return max(1, m)


def _emitidas_pagina_atual_barra(driver) -> int:
    """Página corrente: parâmetro ``pg`` na URL ou item ativo na paginação."""
    u = driver.current_url or ""
    try:
        q = parse_qs(urlparse(u).query)
        if "pg" in q and q["pg"]:
            v = str(q["pg"][0]).strip()
            if v.isdigit():
                return max(1, int(v))
    except Exception:
        pass
    for sel in (
        "ul.pagination li.active a",
        "ul.pagination li.page-item.active a",
        "ul[class*='pagination'] li.active a",
        "ul[class*='pagination'] li.page-item.active a",
    ):
        try:
            act = driver.find_element(By.CSS_SELECTOR, sel)
            t = (act.text or "").strip()
            if t.isdigit():
                return int(t)
        except Exception:
            continue
    return 1


def _emitidas_log_resumo_paginacao(driver, log: Callable[[str], None]) -> None:
    try:
        cur = _emitidas_pagina_atual_barra(driver)
        mx = _emitidas_max_pagina_barra(driver)
        log(f"Paginação: página atual ≈ {cur}; última página com número na barra ≈ {mx}.")
    except Exception:
        pass


def _emitidas_ir_proxima_pagina_via_href_pg(driver, log: Callable[[str], None]) -> bool:
    """
    Emissor Nacional: links ``/EmissorNacional/Notas/Emitidas?pg=N&...`` — mais fiável que só o texto «›».
    """
    cur = _emitidas_pagina_atual_barra(driver)
    want = cur + 1
    for sel in (
        "ul.pagination a[href*='pg=']",
        "ul[class*='pagination'] a[href*='pg=']",
        "nav ul.pagination a[href*='pg=']",
    ):
        for a in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                href = (a.get_attribute("href") or "").strip()
                if "pg=" not in href.lower():
                    continue
                pq = parse_qs(urlparse(href).query)
                if "pg" not in pq or not str(pq["pg"][0]).strip().isdigit():
                    continue
                if int(str(pq["pg"][0]).strip()) != want:
                    continue
                try:
                    li = a.find_element(By.XPATH, "./ancestor::li[1]")
                    if "disabled" in (li.get_attribute("class") or "").lower():
                        continue
                except Exception:
                    pass
                abs_url = urljoin(driver.current_url, href)
                driver.get(abs_url)
                time.sleep(2.6)
                log(f"Paginação: abriu página {want} via URL (pg= na barra).")
                return True
            except Exception:
                continue
    return False


def _emitidas_scroll_area_paginacao(driver) -> None:
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.25)
    except Exception:
        pass
    for sel in (
        "mat-paginator",
        ".mat-mdc-paginator-container",
        "ul.pagination",
        "nav.pagination",
        "ul[class*='pagination']",
        "nav[class*='pagination']",
        ".pagination",
    ):
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if not el.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'end'});", el)
                time.sleep(0.35)
                return
        except Exception:
            continue


def _emitidas_ir_proxima_pagina_via_javascript(driver, log: Callable[[str], None]) -> bool:
    """
    Fallback genérico: localiza listas de paginação visíveis e clica em «>» / «›» ou botão seguinte.
    Cobre variações do Emissor Nacional / Angular em que as classes não são só ``ul.pagination``.
    """
    script = r"""
    function textoVisivel(el) {
      return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    }
    function liDisabled(li) {
      if (!li) return false;
      var c = (li.className || "").toString().toLowerCase();
      return c.indexOf("disabled") >= 0;
    }
    function clickEl(el) {
      try {
        el.scrollIntoView({block: "center", inline: "center"});
        el.click();
        return true;
      } catch (e) {
        try {
          el.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window}));
          return true;
        } catch (e2) { return false; }
      }
    }
    var raw = document.querySelectorAll(
      "ul.pagination, ul[class*='pagination'], nav[class*='pagination'] ul, nav.pagination ul"
    );
    var roots = [];
    for (var z = 0; z < raw.length; z++) {
      if (raw[z].offsetParent) roots.push(raw[z]);
    }
    roots.sort(function(a, b) {
      return b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom;
    });
    for (var r = 0; r < roots.length; r++) {
      var ul = roots[r];
      var rect = ul.getBoundingClientRect();
      if (rect.width < 20 || rect.height < 5) continue;
      var els = ul.querySelectorAll("a, button, span[role='button']");
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var li = el.closest("li");
        if (liDisabled(li)) continue;
        var t = textoVisivel(el);
        var lab = ((el.getAttribute("aria-label") || "") + " " + (el.getAttribute("title") || "") + " " + (el.getAttribute("data-original-title") || "")).toLowerCase();
        if (t === "\u00bb" || t === "\u00ab" || lab.indexOf("\u00faltima") >= 0 || lab.indexOf("ultima") >= 0) continue;
        if (t === ">" || t === "\u203A") {
          if (clickEl(el)) return "arrow";
        }
        if (!t && (lab.indexOf("pr\u00f3xima") >= 0 || lab.indexOf("proxima") >= 0 || (lab.indexOf("next") >= 0 && lab.indexOf("last") < 0))) {
          if (clickEl(el)) return "aria";
        }
      }
    }
    var nb = document.querySelector("button.mat-mdc-paginator-navigation-next:not([disabled])")
      || document.querySelector("button.mat-paginator-navigation-next:not([disabled])");
    if (nb && nb.offsetParent) {
      if (clickEl(nb)) return "mat";
    }
    return "";
    """
    try:
        tag = driver.execute_script(script)
        if tag:
            time.sleep(2.4)
            log("Paginação: página seguinte (deteção JavaScript: %s)." % tag)
            return True
    except Exception:
        pass
    return False


def _emitidas_ir_proxima_pagina_via_item_ativo(driver, log: Callable[[str], None]) -> bool:
    """Clica no ``li`` imediatamente a seguir ao da página ativa (ex.: … 2 3 … quando 2 está ativo → 3)."""
    selectors_active = (
        "ul.pagination a[aria-current='page']",
        "ul[class*='pagination'] a[aria-current='page']",
        "ul.pagination li.page-item.active a",
        "ul.pagination li.active a",
        "ul[class*='pagination'] li.active a",
        "ul[class*='pagination'] li.page-item.active a",
    )
    for sel_act in selectors_active:
        try:
            act = driver.find_element(By.CSS_SELECTOR, sel_act)
            li_act = act.find_element(By.XPATH, "./ancestor::li[1]")
            nxt = li_act.find_element(By.XPATH, "following-sibling::li[1]")
            if "disabled" in (nxt.get_attribute("class") or "").lower():
                continue
            for sub in ("a", "button"):
                try:
                    el = nxt.find_element(By.CSS_SELECTOR, sub)
                    if not el.is_displayed():
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    try:
                        el.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", el)
                    time.sleep(2.4)
                    log("Paginação: clique no número/tab seguinte ao item ativo.")
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _emitidas_ir_proxima_pagina(driver, wait, log: Callable[[str], None]) -> bool:
    """Clica em «próxima página» (Material, PrimeFaces ou Bootstrap). Retorna False se não houver."""
    _emitidas_scroll_area_paginacao(driver)

    # Emissor Nacional: links ``?pg=N&datainicio=...`` — prioridade sobre «›» (Bootstrap).
    if "emitidas" in (driver.current_url or "").lower():
        if _emitidas_ir_proxima_pagina_via_href_pg(driver, log):
            return True

    if _emitidas_ir_proxima_pagina_via_javascript(driver, log):
        return True
    if _emitidas_ir_proxima_pagina_via_item_ativo(driver, log):
        return True

    # Bootstrap (Emissor Nacional): « < 1 2 3 > » — o texto da âncora «seguinte» costuma ser «>» ou «›».
    try:
        for ul in driver.find_elements(
            By.CSS_SELECTOR,
            "ul.pagination, nav ul.pagination, ul[class*='pagination'], nav[class*='pagination'] ul",
        ):
            if not ul.is_displayed():
                continue
            for a in ul.find_elements(
                By.CSS_SELECTOR,
                "li.page-item:not(.disabled) a.page-link, li:not(.disabled) a, li:not(.disabled) button",
            ):
                try:
                    li = a.find_element(By.XPATH, "./..")
                    if "disabled" in (li.get_attribute("class") or "").lower():
                        continue
                except Exception:
                    pass
                t = (a.text or "").strip()
                aria = (
                    (a.get_attribute("aria-label") or "")
                    + " "
                    + (a.get_attribute("title") or "")
                    + " "
                    + (a.get_attribute("data-original-title") or "")
                ).lower()
                if t in (">", "›", "\u203a") or (
                    not t and ("próxim" in aria or "proxim" in aria or "next" in aria) and "last" not in aria
                ):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
                    except Exception:
                        pass
                    try:
                        a.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", a)
                    time.sleep(2.2)
                    log("Paginação: página seguinte (Bootstrap ul.pagination).")
                    return True
    except Exception:
        pass

    for sel in (
        "button.mat-mdc-paginator-navigation-next:not([disabled])",
        "button.mat-paginator-navigation-next:not([disabled])",
    ):
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    try:
                        el.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", el)
                    time.sleep(2.0)
                    log("Paginação: página seguinte (Material).")
                    return True
        except Exception:
            continue

    try:
        el = driver.find_element(By.CSS_SELECTOR, ".ui-paginator-next:not(.ui-state-disabled)")
        if el.is_displayed():
            el.click()
            time.sleep(2.0)
            log("Paginação: página seguinte (PrimeFaces).")
            return True
    except Exception:
        pass

    xpaths = (
        "//ul[contains(@class,'pagination')]/li[not(contains(@class,'disabled'))]/a[normalize-space(.)='›']",
        "//ul[contains(@class,'pagination')]/li[not(contains(@class,'disabled'))]/a[normalize-space(.)='>']",
        "//nav//ul[contains(@class,'pagination')]//a[normalize-space(.)='›']",
        "//a[normalize-space(.)='›']",
        "//button[contains(@aria-label,'Next') and not(@disabled)]",
        "//button[contains(@aria-label,'Próxima') or contains(@aria-label,'Proxima')]",
        "//ul[contains(@class,'pagination')]//a[contains(@title,'Próxima') or contains(@title,'Proxima') or contains(@data-original-title,'Próxima') or contains(@data-original-title,'Proxima')]",
    )
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if not el.is_displayed():
                    continue
                if (el.get_attribute("disabled") or "").lower() in ("true", "disabled"):
                    continue
                try:
                    li = el.find_element(By.XPATH, "./ancestor::li[1]")
                    if "disabled" in (li.get_attribute("class") or "").lower():
                        continue
                except Exception:
                    pass
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                except Exception:
                    pass
                try:
                    el.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", el)
                time.sleep(2.2)
                log("Paginação: clique em «seguinte».")
                return True
        except Exception:
            continue
    return False


def _emitidas_baixar_xml_e_danfs_por_linhas(
    driver,
    wait,
    log: Callable[[str], None],
    *,
    max_linhas: int = 250,
    download_dir: Path | None = None,
) -> int:
    try:
        wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "table.table-striped tbody tr, mat-table mat-row, table tbody tr, [role='grid'] [role='row']",
                )
            )
        )
    except TimeoutException:
        pass

    rows = _emitidas_coletar_linhas(driver, log)
    if not rows:
        log("Nenhuma linha de notas encontrada após Filtrar (tabela Angular ou HTML mudou).")
        return 0

    n = min(len(rows), max_linhas)
    ok = 0
    for i in range(n):
        rows = _emitidas_coletar_linhas(driver, log)
        if i >= len(rows):
            break
        row = rows[i]
        web_k = _emitidas_web_chave_tr(row)
        cancel_portal, situ = _emitidas_linha_portal_nfse_cancelada(row)
        dd0 = Path(download_dir) if download_dir else None
        if dd0 and web_k and emitidas_portal_manifest_web_chave_ja_listada(dd0, web_k):
            log(f"Linha {i + 1}: data-chave já baixada (manifesto) — ignorando download.")
            continue
        chave = _chave44_na_linha(row)
        if dd0 and chave and emitidas_portal_manifest_chave44_ja_baixada(dd0, chave):
            log(f"Linha {i + 1}: chave 44 já no manifesto — ignorando download.")
            continue
        if chave and _emitidas_xml_ja_baixado(download_dir, chave):
            log(f"Linha {i + 1}: chave {chave[:10]}… — XML já na pasta, ignorando download.")
            continue
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
        except Exception:
            pass

        menu_btn = None
        sub_selectors = (
            "td.td-opcoes .menu-suspenso-tabela button",
            "td.td-opcoes .menu-suspenso-tabela a",
            "td.td-opcoes button.dropdown-toggle",
            "td.td-opcoes button",
            ".menu-suspenso-tabela button",
            "button[aria-haspopup='menu']",
            "button[aria-haspopup='true']",
            "button.mat-mdc-menu-trigger",
            "mat-cell:last-child button",
            "td:last-child button",
        )
        for css in sub_selectors:
            try:
                subs = row.find_elements(By.CSS_SELECTOR, css)
                for sub in subs:
                    if sub.is_displayed():
                        menu_btn = sub
                        break
                if menu_btn:
                    break
            except StaleElementReferenceException:
                rows = _emitidas_coletar_linhas(driver, log)
                if i < len(rows):
                    row = rows[i]
                continue
        if menu_btn is None:
            log(f"Linha {i + 1}: menu (⋮) não encontrado.")
            continue
        try:
            menu_btn.click()
            time.sleep(0.65)
        except Exception as ex:
            log(f"Linha {i + 1}: falha ao abrir menu ({ex}).")
            continue

        xml_paths_antes: set[str] = set()
        pdf_paths_antes: set[str] = set()
        novo_p: Path | None = None
        if download_dir:
            dd = Path(download_dir)
            xml_paths_antes = {str(p.resolve()) for p in dd.glob("*.xml")}
            pdf_paths_antes = {str(p.resolve()) for p in dd.glob("*.pdf")}

        if not _emitidas_clicar_download_menu(driver, r"Download\s*XML", log, row_el=row):
            log(f"Linha {i + 1}: opção Download XML não encontrada.")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")  # Escape
            except Exception:
                pass
            continue

        chave44_m: str | None = None
        xml_bytes = b""
        if download_dir:
            novo_p = _emitidas_aguardar_novo_xml(Path(download_dir), xml_paths_antes, log)
            if novo_p:
                try:
                    xml_bytes = novo_p.read_bytes()
                    chave44_m = extrair_chave_acesso_nfse_xml(xml_bytes)
                    if not chave44_m:
                        stem = novo_p.stem.strip()
                        if re.fullmatch(r"\d{44}", stem):
                            chave44_m = stem
                except Exception as ex:
                    xml_bytes = b""
                    log(f"Linha {i + 1}: aviso ao extrair chave do XML ({ex}).")
            elif cancel_portal:
                log(
                    f"Linha {i + 1}: situação cancelada no portal ({situ!r}), mas o .xml não surgiu a tempo — "
                    "pode falhar gravar em Cancelada/ para esta linha."
                )

        if download_dir and chave44_m and emitidas_portal_manifest_chave44_ja_baixada(Path(download_dir), chave44_m):
            log(
                f"Linha {i + 1}: o XML obtido é de uma NF já manifestada ({chave44_m[:10]}…) — "
                "download duplicado; não repetir DANFS-e."
            )
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
            except Exception:
                pass
            continue

        cancel_xml = bool(xml_bytes) and xml_nfse_portal_indica_cancelada(xml_bytes)
        # A pasta ``Cancelada/`` segue só a grelha «Emitidas» (``data-situacao`` / célula de situação). O XML do
        # «Download» costuma ser o DPS sem evento de cancelamento — nunca o usar para recusar ``Cancelada/``.
        cancelada_efetiva = bool(cancel_portal)

        if cancelada_efetiva:
            extra = " (XML também indica cancelamento)" if cancel_xml else ""
            log(f"Linha {i + 1}: nota cancelada no portal ({situ!r}){extra} — ficheiros para Cancelada/.")

        if download_dir and novo_p and (chave44_m or web_k):
            try:
                emitidas_portal_manifest_append(
                    Path(download_dir),
                    chave44=chave44_m,
                    cancelada_portal=cancelada_efetiva,
                    web_chave=web_k or None,
                )
            except Exception as ex:
                log(f"Linha {i + 1}: aviso ao gravar manifesto (após XML) ({ex}).")

        try:
            rows = _emitidas_coletar_linhas(driver, log)
            if i < len(rows):
                row = rows[i]
            menu_btn = None
            for css in sub_selectors:
                for sub in row.find_elements(By.CSS_SELECTOR, css):
                    if sub.is_displayed():
                        menu_btn = sub
                        break
                if menu_btn:
                    break
            if menu_btn:
                menu_btn.click()
                time.sleep(0.65)
        except Exception:
            pass

        if not _emitidas_clicar_download_menu(driver, r"Download\s*DANFS", log, row_el=row):
            _emitidas_clicar_download_menu(driver, r"DANFS\s*-?\s*e", log, row_el=row)

        try:
            driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
        except Exception:
            pass
        time.sleep(0.45)
        time.sleep(0.85)
        if download_dir:
            _emitidas_mover_baixados_para_cancelada(
                Path(download_dir),
                cancelada_efetiva,
                novo_p,
                pdf_paths_antes,
                log,
                f"Linha {i + 1}",
            )
            try:
                emitidas_portal_manifest_append(
                    Path(download_dir),
                    chave44=chave44_m,
                    cancelada_portal=cancelada_efetiva,
                    web_chave=web_k or None,
                )
            except Exception as ex:
                log(f"Linha {i + 1}: aviso ao gravar manifesto do portal ({ex}).")
        ok += 1
        log(f"Linha {i + 1}/{n}: XML e DANFS-e solicitados.")

    return ok


def run_emitidas_selenium(
    login: str,
    senha: str,
    data_inicio: date,
    data_fim: date,
    *,
    headless: bool = False,
    pausa_interativa: bool = False,
    log: Callable[[str], None] = print,
    download_dir: Path | None = None,
    perfil_persistente: bool | None = None,
) -> Path:
    """
    Abre Chrome ou Edge (Selenium): com ``--perfil`` / ``persistent_context``, usa ``user-data-dir`` dedicado.

    Grava downloads em ``download_dir`` (ou temp). Retorna esse diretório.
    """
    cfg: dict[str, Any] = dict(_cfg())
    if perfil_persistente is False:
        cfg["persistent_context"] = False
    elif perfil_persistente is True:
        cfg["persistent_context"] = True

    login_url = (cfg.get("login_url") or "https://www.nfse.gov.br/EmissorNacional/Login").strip()
    timeout_sec = max(5.0, float(cfg.get("timeout_ms") or 60000) / 1000.0)

    user_selectors: list[str] = list(cfg.get("user_selectors") or [])
    password_selector = (cfg.get("password_selector") or 'input[type="password"]').strip()
    submit_selectors: list[str] = list(
        cfg.get("submit_selectors")
        or [
            'button:has-text("Entrar")',
            'button:has-text("Acessar")',
            'button:has-text("Continuar")',
            'button:has-text("Avançar")',
            'input[type="submit"]',
            'button[type="submit"]',
        ]
    )
    emitidas_texts: list[str] = list(
        cfg.get("emitidas_link_texts")
        or [
            "Notas emitidas",
            "Notas Emitidas",
            "NFS-e emitidas",
            "NFS-e Emitidas",
            "Emitidas",
            "Consultar NFSe",
            "Pesquisar NFSe",
            "NFSe",
            "DFe",
        ]
    )
    after_emit_url = (cfg.get("after_login_emitidas_url") or "").strip()

    out_dir = download_dir or Path(tempfile.mkdtemp(prefix="nfse_portal_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    emitidas_portal_manifest_limpar(out_dir)

    use_p, prof_dir, ch_cfg = _persistent_profile(cfg, log)
    browser_ch = ((ch_cfg or cfg.get("browser_channel") or "") or "chrome").strip().lower()
    if browser_ch not in ("chrome", "msedge"):
        browser_ch = "chrome"

    temp_profile_to_cleanup: Path | None = None
    if use_p and prof_dir is not None:
        prof_dir.mkdir(parents=True, exist_ok=True)
        user_data_arg = str(prof_dir)
        log(
            f"Selenium: perfil persistente ({browser_ch}) em {prof_dir} — "
            "feche outro navegador que use a mesma pasta de perfil."
        )
    else:
        temp_profile_to_cleanup = Path(tempfile.mkdtemp(prefix="nfse_sel_prof_"))
        user_data_arg = str(temp_profile_to_cleanup)
        log("Selenium: perfil temporário (sessão limpa; sem extensões herdadas do seu Chrome diário).")

    chrome_prefs = {
        "download.default_directory": str(out_dir.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }

    driver = None
    try:
        if browser_ch == "msedge":
            from selenium.webdriver.edge.options import Options as EdgeOptions

            opts = EdgeOptions()
        else:
            from selenium.webdriver.chrome.options import Options as ChromeOptions

            opts = ChromeOptions()

        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1360,900")
        opts.add_argument(f"--user-data-dir={user_data_arg}")
        opts.add_argument("--no-sandbox")
        opts.add_experimental_option("prefs", chrome_prefs)
        if headless:
            opts.add_argument("--headless=new")

        log(f"Abrindo navegador ({browser_ch}) …")
        if browser_ch == "msedge":
            driver = webdriver.Edge(options=opts)
        else:
            driver = webdriver.Chrome(options=opts)

        driver.set_page_load_timeout(timeout_sec)
        wait = _wait(driver, min(30.0, timeout_sec))

        log(f"Abrindo {login_url} …")
        driver.get(login_url)
        time.sleep(1)
        try:
            wait.until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, 'input[type="password"], input[type="text"], input[type="email"]')
                )
            )
        except TimeoutException:
            log("Aviso: formulário de login pode ainda estar a carregar (SPA).")

        if not _tentar_preencher_login(driver, wait, login, log, user_selectors, timeout_sec):
            _screenshot_erro(driver, out_dir, "portal_erro_campo_login.png", log)
            raise RuntimeError(
                "Não foi possível localizar o campo de login (usuário/CPF/CNPJ). "
                "Defina NFSE_PORTAL_PLAYWRIGHT['user_selectors'] em settings.py com o seletor CSS do campo. "
                "Consulte portal_erro_campo_login.png na pasta de downloads da execução."
            )

        if not _fill_password(driver, password_selector, senha, log):
            _screenshot_erro(driver, out_dir, "portal_erro_campo_senha.png", log)
            raise RuntimeError(
                f"Campo de senha não encontrado ({password_selector!r}). "
                "Ajuste NFSE_PORTAL_PLAYWRIGHT['password_selector']. Ver portal_erro_campo_senha.png."
            )

        if not _click_submit_login(driver, wait, submit_selectors, timeout_sec, log):
            _screenshot_erro(driver, out_dir, "portal_erro_botao_entrar.png", log)
            raise RuntimeError(
                "Botão de envio do login não encontrado. "
                "Defina NFSE_PORTAL_PLAYWRIGHT['submit_selectors'] em settings. Ver portal_erro_botao_entrar.png."
            )

        time.sleep(2)
        log("Aguardando navegação pós-login …")
        time.sleep(2)

        nav_ok = _navegar_emitidas_com_periodo(
            driver, wait, data_inicio, data_fim, after_emit_url, cfg, timeout_sec, log
        )
        cur = (driver.current_url or "").lower()
        if not nav_ok or "emitidas" not in cur:
            _emitidas_fallback_menu_principal(driver, wait, emitidas_texts, after_emit_url, timeout_sec, log)
            if "emitidas" not in (driver.current_url or "").lower():
                _navegar_emitidas_com_periodo(driver, wait, data_inicio, data_fim, "", cfg, timeout_sec, log)

        _emitidas_preencher_campos_e_filtrar(driver, wait, data_inicio, data_fim, timeout_sec, log)
        max_linhas_global = int(cfg.get("emitidas_max_linhas") or 500)
        max_por_pagina = int(cfg.get("emitidas_max_linhas_por_pagina") or 250)
        max_paginas = int(cfg.get("emitidas_max_paginas") or 80)
        total_proc = 0
        pag_idx = 0
        _emitidas_log_resumo_paginacao(driver, log)
        while pag_idx < max_paginas and total_proc < max_linhas_global:
            pag_idx += 1
            restante = max_linhas_global - total_proc
            limite_pag = min(max_por_pagina, restante)
            nproc = _emitidas_baixar_xml_e_danfs_por_linhas(
                driver,
                wait,
                log,
                max_linhas=limite_pag,
                download_dir=out_dir,
            )
            total_proc += nproc
            log(
                f"Página {pag_idx}: {nproc} nota(s) com download solicitado "
                f"(acumulado {total_proc}, limite {max_linhas_global})."
            )
            if total_proc >= max_linhas_global:
                break
            if not _emitidas_ir_proxima_pagina(driver, wait, log):
                log(
                    f"Paginação: fim (página ≈ {_emitidas_pagina_atual_barra(driver)}, "
                    f"última com número na barra ≈ {_emitidas_max_pagina_barra(driver)}). "
                    "Sem «Próxima» ativa nem link pg=N+1 — ou limite emitidas_max_paginas."
                )
                break
            time.sleep(2.8)
            try:
                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "table.table-striped tbody tr, mat-table mat-row, table tbody tr, [role='grid'] [role='row']",
                        )
                    )
                )
            except TimeoutException:
                pass
        log(f"Processamento da grade concluído: {total_proc} download(s) no total.")
        time.sleep(3)

        try:
            shot = out_dir / "portal_apos_cliques.png"
            driver.save_screenshot(str(shot))
            log(f"Screenshot de referência: {shot}")
        except Exception:
            pass

        aguardar_max = min(120.0, max(30.0, float(timeout_sec) * 1.5))

        if not headless:
            if pausa_interativa:
                log(
                    "Pausa: navegue no portal se precisar. Prima Enter para fechar o Chrome; "
                    "em seguida o comando importa os XML da pasta do mês."
                )
                try:
                    input()
                except EOFError:
                    pass
            else:
                log(
                    "A aguardar conclusão dos ficheiros na pasta de download (até os .crdownload terminarem)…"
                )
                _aguardar_pasta_sem_crdownload(out_dir, aguardar_max, log)
                if driver is not None:
                    try:
                        log("A fechar o Chrome…")
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
                    log("Chrome fechado.")
        else:
            log("Modo headless: a aguardar downloads na pasta…")
            _aguardar_pasta_sem_crdownload(out_dir, min(aguardar_max, 90.0), log)
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        if temp_profile_to_cleanup is not None and temp_profile_to_cleanup.exists():
            try:
                shutil.rmtree(temp_profile_to_cleanup, ignore_errors=True)
            except Exception:
                pass

    return out_dir
