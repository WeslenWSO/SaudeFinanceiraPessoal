"""
[Legado] Automação com Playwright. O fluxo ativo da aplicação passou a usar ``portal_emitidas_selenium``.

Automação opcional do site Emissor Nacional (login + tentativa de notas emitidas + XML/PDF).

Dependência: ``pip install playwright``; Chromium: ``playwright install chromium``; perfil Chrome/Edge:
``playwright install chrome`` (ou ``msedge``).

O HTML do portal pode mudar ou exigir Gov.br / certificado — use ``NFSE_PORTAL_PLAYWRIGHT`` em settings
para ajustar seletores ou ``after_login_emitidas_url`` (URL da tela após logar, copiada do Chrome).

Com **perfil persistente** (``NFSE_PORTAL_PLAYWRIGHT['persistent_context']=True`` ou ``--perfil`` no comando),
o Playwright usa **Chrome ou Edge instalado** e pasta de perfil dedicada (extensões após instalar uma vez).

Com ``persistent_context`` falso (defeito em ``settings``), usa-se o **Chromium empacotado** (sem extensões da loja).
"""
from __future__ import annotations

import os
import re
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from django.conf import settings as django_settings


def _cfg() -> dict[str, Any]:
    d = getattr(django_settings, "NFSE_PORTAL_PLAYWRIGHT", None) or {}
    if not isinstance(d, dict):
        return {}
    return d


def diagnostico_playwright_carregavel() -> tuple[bool, str]:
    """
    Verifica se ``playwright.sync_api`` consegue importar neste interpretador (DLL/greenlet, pacote em falta).

    Retorna ``(True, "")`` ou ``(False, mensagem)`` — mensagem em português, várias linhas, para alerta na UI.
    """
    import sys

    exe = sys.executable
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ModuleNotFoundError as e:
        return False, (
            "O pacote «playwright» não está instalado neste Python.\n\n"
            f"Detalhe: {e}\n\n"
            f"Interpretador em uso: {exe}\n\n"
            "No mesmo ambiente onde corre o «runserver», execute:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )
    except ImportError as e:
        err = str(e)
        low = err.lower()
        bloco = [
            "O Playwright não conseguiu carregar (falha em biblioteca nativa / DLL).",
            f"Detalhe: {err}",
            "",
            f"Interpretador em uso: {exe}",
            "",
        ]
        if "bloqueou" in low or "applocker" in low or "controle de aplicativo" in low:
            bloco.append(
                "O Windows (Controlo de aplicações, AppLocker ou antivírus) bloqueou um ficheiro "
                "(muitas vezes «greenlet» ou «playwright»). Peça ao administrador de TI para autorizar esta "
                "instalação de Python ou a pasta do projeto."
            )
            el = exe.lower().replace("/", "\\")
            if "onedrive" in el:
                bloco.extend(
                    [
                        "",
                        "O interpretador está dentro do OneDrive (Documentos sincronizados). Isso é uma causa "
                        "muito comum de bloqueio de DLLs. Copie o projeto para uma pasta **local**, fora do "
                        "OneDrive (ex.: C:\\Dev\\SaudeFinanceira), crie de novo a venv («python -m venv venv»), "
                        "instale dependências e volte a correr o servidor.",
                    ]
                )
            bloco.extend(
                [
                    "",
                    "Em PCs geridos: o TI pode criar uma regra AppLocker/WDAC para o Python da venv ou para "
                    "«greenlet» / «playwright». Em Defender pessoal, às vezes ajuda uma exclusão na pasta "
                    "«venv\\Lib\\site-packages» (depende da política).",
                ]
            )
        elif "dll" in low or "greenlet" in low:
            bloco.append(
                "Tente reinstalar as dependências nativas:\n"
                "  pip install --force-reinstall greenlet\n"
                "  pip install -U playwright\n"
                "  playwright install chromium"
            )
        else:
            bloco.append(
                "Reinstale o Playwright e o navegador de teste:\n"
                "  pip install --force-reinstall playwright greenlet\n"
                "  playwright install chromium"
            )
        return False, "\n".join(bloco)
    except Exception as e:
        return False, (
            f"Erro ao carregar o Playwright: {e}\n\nInterpretador em uso: {exe}"
        )
    return True, ""


def _log(fn: Callable[[str], None], msg: str) -> None:
    fn(msg)


def _playwright_persistent_profile(cfg: dict[str, Any], log: Callable[[str], None]) -> tuple[bool, Path | None, str | None]:
    """
    Perfil em disco para ``launch_persistent_context`` (Chrome/Edge instalado — extensões e cookies persistem).

    - ``persistent_context`` em settings: só ``True`` liga; ``False`` ou ausente desliga (Chromium empacotado).
    - ``persistent_user_data_dir``: vazio → ``~/.saude_financeira/playwright_nfse_profile`` (não use o mesmo
      diretório do Chrome do dia a dia com o Chrome já aberto — bloqueio de perfil).
    - ``browser_channel``: ``chrome`` ou ``msedge`` (padrão ``chrome`` com perfil persistente).
    """
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
        _log(
            log,
            f"Perfil persistente exige browser_channel «chrome» ou «msedge» (recebido: {ch!r}); "
            "usando Chromium empacotado sem perfil.",
        )
        return False, None, ch_cfg

    return True, user_data, ch


def _pw_close(context: Any, browser: Any, log: Callable[[str], None]) -> None:
    try:
        if context is not None:
            context.close()
    except Exception as ex:
        _log(log, f"Aviso ao fechar contexto Playwright: {ex}")
    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass


def _emitidas_url_base(cfg: dict[str, Any]) -> str:
    u = (cfg.get("emitidas_page_url") or "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas").strip()
    return u.split("?", 1)[0].rstrip("/")


def _navegar_emitidas_com_periodo(page, data_inicio: date, data_fim: date, after_emit_url: str, cfg: dict[str, Any], timeout_ms: int, log: Callable[[str], None]) -> bool:
    """Abre a lista de emitidas com datainicio/datafim (dd/mm/aaaa) na query, conforme o portal nacional."""
    di_br = data_inicio.strftime("%d/%m/%Y")
    df_br = data_fim.strftime("%d/%m/%Y")
    if (data_fim - data_inicio).days > 31:
        _log(
            log,
            "Aviso: o portal costuma limitar o filtro a ~30 dias; reduza o período se o resultado vier vazio.",
        )
    if after_emit_url:
        try:
            _log(log, f"Abrindo after_login_emitidas_url …")
            page.goto(after_emit_url, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(2)
            return True
        except Exception as ex:
            _log(log, f"Aviso: after_login_emitidas_url falhou ({ex}); tentando URL padrão com período.")
    base = _emitidas_url_base(cfg)
    qs = urlencode({"datainicio": di_br, "datafim": df_br})
    url = f"{base}?{qs}"
    try:
        _log(log, f"Abrindo lista de emitidas com período: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        time.sleep(2.5)
        return True
    except Exception as ex:
        _log(log, f"Aviso: goto emitidas falhou ({ex}).")
        return False


def _emitidas_preencher_campos_e_filtrar(page, data_inicio: date, data_fim: date, timeout_ms: int, log: Callable[[str], None]) -> None:
    """Preenche Data Inicial / Data Final (pt-BR ou type=date) e clica em Filtrar."""
    di_br = data_inicio.strftime("%d/%m/%Y")
    df_br = data_fim.strftime("%d/%m/%Y")
    di_iso = data_inicio.isoformat()
    df_iso = data_fim.isoformat()

    for lab in (re.compile(r"data\s*inicial", re.I), re.compile(r"^\s*Data\s+Inicial\s*$", re.I)):
        try:
            loc = page.get_by_label(lab).first
            if loc.count() > 0:
                loc.click(timeout=2000)
                loc.fill("", timeout=1000)
                loc.fill(di_br, timeout=3000)
                _log(log, f"Data inicial preenchida ({lab.pattern}).")
                break
        except Exception:
            continue

    for lab in (re.compile(r"data\s*final", re.I), re.compile(r"^\s*Data\s+Final\s*$", re.I)):
        try:
            loc = page.get_by_label(lab).first
            if loc.count() > 0:
                loc.click(timeout=2000)
                loc.fill("", timeout=1000)
                loc.fill(df_br, timeout=3000)
                _log(log, f"Data final preenchida ({lab.pattern}).")
                break
        except Exception:
            continue

    try:
        dates = page.locator('input[type="date"]')
        n = dates.count()
        if n >= 2:
            dates.nth(0).fill(di_iso, timeout=3000)
            dates.nth(1).fill(df_iso, timeout=3000)
            _log(log, "Campos type=date preenchidos (ISO).")
        elif n == 1:
            dates.first.fill(di_iso, timeout=3000)
    except Exception as ex:
        _log(log, f"Aviso: inputs type=date ({ex}).")

    try:
        ph = page.get_by_placeholder(re.compile(r"dd/mm|__/", re.I))
        if ph.count() >= 2:
            ph.nth(0).fill(di_br, timeout=3000)
            ph.nth(1).fill(df_br, timeout=3000)
            _log(log, "Datas preenchidas por placeholder.")
    except Exception:
        pass

    try:
        page.get_by_role("button", name=re.compile(r"Filtrar", re.I)).first.click(timeout=8000)
        _log(log, "Clique em Filtrar.")
        time.sleep(2.5)
        try:
            page.wait_for_load_state("networkidle", timeout=min(25000, timeout_ms))
        except Exception:
            pass
    except Exception as ex:
        _log(log, f"Aviso: botão Filtrar não encontrado ou falhou ({ex}).")


def _emitidas_overlay_menu_root(page):
    """Painel do menu (⋮) costuma ir para ``cdk-overlay-container`` fora da linha."""
    return page.locator(
        ".cdk-overlay-container .mat-mdc-menu-panel, "
        ".cdk-overlay-container mat-menu-panel, "
        ".cdk-overlay-container [role='menu']"
    ).last


def _emitidas_clicar_download_menu(
    page,
    label_pattern: str,
    log: Callable[[str], None],
    *,
    row=None,
) -> bool:
    """
    Clica em «Download XML» / «Download DANFS-e» no menu aberto.
    O portal pode usar tabela HTML (``td.td-opcoes`` / ``menu-suspenso-tabela``) ou Angular (overlay).
    """
    pat = re.compile(label_pattern, re.I)
    overlay = _emitidas_overlay_menu_root(page)

    def _try_click(locator) -> bool:
        try:
            if locator.count() == 0:
                return False
            el = locator.first
            if not el.is_visible():
                return False
            el.click(timeout=8000)
            _log(log, f"Menu: clique em «{label_pattern}».")
            time.sleep(1.2)
            return True
        except Exception:
            return False

    # 1) Tabela listrada (Emissor nacional): opções na própria linha
    if row is not None:
        td_op = row.locator("td.td-opcoes")
        for inner in (
            td_op.locator("a, button").filter(has_text=pat),
            row.locator(".menu-suspenso-tabela a, .menu-suspenso-tabela button").filter(has_text=pat),
            row.locator(".dropdown-menu a, .dropdown-menu button").filter(has_text=pat),
            td_op.get_by_role("link", name=pat),
            td_op.get_by_role("menuitem", name=pat),
        ):
            if _try_click(inner):
                return True

    # 2) Angular Material: painel no CDK overlay
    if _try_click(overlay.get_by_role("menuitem", name=pat)):
        return True
    if _try_click(overlay.locator("button, a[role='menuitem'], [role='menuitem']").filter(has_text=pat)):
        return True
    if _try_click(overlay.locator("button.mat-mdc-menu-item, .mat-mdc-menu-item").filter(has_text=pat)):
        return True

    # 3) Dropdown Bootstrap visível (menu pode teletransportar-se para o body)
    if _try_click(page.locator(".dropdown-menu.show a, .dropdown-menu.show button").filter(has_text=pat)):
        return True

    for fn in (
        lambda: page.get_by_role("menuitem", name=pat).first,
        lambda: page.get_by_role("link", name=pat).first,
        lambda: page.get_by_role("button", name=pat).first,
        lambda: page.get_by_text(pat).first,
    ):
        if _try_click(fn()):
            return True
    return False


def _emitidas_coletar_linhas_tabela(page, log: Callable[[str], None]):
    """
    Linhas de dados na lista «Notas emitidas».
    HTML típico: ``table.table-striped tbody tr`` com ``td.td-opcoes`` / ``div.menu-suspenso-tabela``.
    Alternativa: Angular Material ``mat-row`` / ``mat-cell``.
    """
    specs: list[tuple[str, str | None]] = [
        ("table.table-striped tbody tr", "td.td-opcoes"),
        ("table.table-striped tbody tr", "td"),
        ("mat-table mat-row", "mat-cell"),
        ("tbody[role='rowgroup'] tr", "td"),
        ("table tbody tr", "td"),
        ("table tbody tr", None),
        ("[role='grid'] [role='row']", "[role='gridcell']"),
    ]
    for sel, cell in specs:
        try:
            loc = page.locator(sel)
            if cell:
                loc = loc.filter(has=page.locator(cell))
            n = loc.count()
            if n > 0:
                _log(log, f"Tabela de notas: «{sel}»" + (f" com «{cell}»" if cell else "") + f" ({n} linha(s)).")
                return loc
        except Exception:
            continue
    return None


def _emitidas_baixar_xml_e_danfs_por_linhas(
    page,
    log: Callable[[str], None],
    *,
    max_linhas: int = 250,
) -> int:
    """
    Para cada linha da tabela de notas: abre o menu (⋮), Download XML, abre de novo, Download DANFS-e.
    Os arquivos são gravados pelo handler de download do contexto (pasta temporária).
    Retorna quantidade de linhas processadas.
    """
    try:
        page.locator(
            "table.table-striped tbody tr, mat-table mat-row, table tbody tr, [role='grid'] [role='row']"
        ).first.wait_for(state="visible", timeout=20000)
    except Exception:
        pass

    rows = _emitidas_coletar_linhas_tabela(page, log)
    if rows is None or rows.count() == 0:
        _log(log, "Nenhuma linha de notas encontrada após Filtrar (tabela Angular ou HTML mudou).")
        return 0

    n = min(rows.count(), max_linhas)
    ok = 0
    for i in range(n):
        row = rows.nth(i)
        try:
            row.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass

        menu_btn = None
        for sub in (
            row.locator("td.td-opcoes .menu-suspenso-tabela button").first,
            row.locator("td.td-opcoes .menu-suspenso-tabela a").first,
            row.locator("td.td-opcoes button.dropdown-toggle").first,
            row.locator("td.td-opcoes button").first,
            row.locator(".menu-suspenso-tabela button, .menu-suspenso-tabela a").first,
            row.locator("button[aria-haspopup='menu']").first,
            row.locator("button[aria-haspopup='true']").first,
            row.locator("button.mat-mdc-menu-trigger").first,
            row.locator("mat-cell:last-child button").last,
            row.locator("td:last-child button").last,
            row.locator("button").filter(has=page.locator("mat-icon, .mat-icon, svg")).last,
            row.get_by_role("button").last,
        ):
            try:
                if sub.count() > 0 and sub.first.is_visible():
                    menu_btn = sub
                    break
            except Exception:
                continue
        if menu_btn is None or menu_btn.count() == 0:
            _log(log, f"Linha {i + 1}: menu (⋮) não encontrado.")
            continue
        try:
            menu_btn.click(timeout=5000)
            time.sleep(0.65)
        except Exception as ex:
            _log(log, f"Linha {i + 1}: falha ao abrir menu ({ex}).")
            continue

        if not _emitidas_clicar_download_menu(page, r"Download\s*XML", log, row=row):
            _log(log, f"Linha {i + 1}: opção Download XML não encontrada.")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            continue

        try:
            menu_btn.click(timeout=5000)
            time.sleep(0.65)
        except Exception:
            try:
                row.scroll_into_view_if_needed()
                menu_btn.click(timeout=4000)
                time.sleep(0.65)
            except Exception:
                pass

        if not _emitidas_clicar_download_menu(page, r"Download\s*DANFS", log, row=row):
            _emitidas_clicar_download_menu(page, r"DANFS\s*-?\s*e", log, row=row)

        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        time.sleep(0.45)
        ok += 1
        _log(log, f"Linha {i + 1}/{n}: XML e DANFS-e solicitados.")

    return ok


def _emitidas_fallback_menu_principal(
    page,
    emitidas_texts: list[str],
    after_emit_url: str,
    timeout_ms: int,
    log: Callable[[str], None],
) -> bool:
    """Se a URL direta falhar, tenta links do menu (comportamento antigo)."""
    if after_emit_url:
        return False
    opened = False
    for label in emitidas_texts:
        if len((label or "").strip()) < 2:
            continue
        pat = re.compile(re.escape(label.strip()), re.I)
        try:
            lk = page.get_by_role("link", name=pat)
            if lk.count() > 0:
                lk.first.click(timeout=5000)
                opened = True
                _log(log, f"Clique em link: {label!r}")
                time.sleep(1.5)
                break
        except Exception:
            pass
    if not opened:
        for href_part in ("emitid", "emitida", "Notas/Emitidas"):
            try:
                loc = page.locator(f'a[href*="{href_part}"]').first
                if loc.count() > 0:
                    loc.click(timeout=5000)
                    opened = True
                    _log(log, f"Clique em link href*={href_part!r}")
                    time.sleep(1.5)
                    break
            except Exception:
                continue
    return opened


def _tentar_preencher_login(
    page,
    login: str,
    log: Callable[[str], None],
    user_selectors: list[str],
) -> bool:
    """
    Preenche o campo de usuário/CPF/CNPJ na tela de login.
    Ordem: seletores explícitos em settings → seletores comuns do Emissor Nacional → heurísticas.
    """
    for sel in user_selectors:
        if not (sel or "").strip():
            continue
        try:
            base = page.locator(sel.strip())
            if base.count() > 0:
                el = base.first
                if el.is_visible():
                    el.fill("", timeout=2000)
                    el.fill(login, timeout=8000)
                    _log(log, f"Login preenchido (user_selectors: {sel!r}).")
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
            base = page.locator(sel)
            if base.count() > 0:
                el = base.first
                if el.is_visible():
                    el.fill("", timeout=2000)
                    el.fill(login, timeout=8000)
                    _log(log, f"Login preenchido (seletor {sel!r}).")
                    return True
        except Exception:
            continue

    for lab in (
        re.compile(r"usu[aá]rio|login|cpf|cnpj|e-?mail", re.I),
        re.compile(r"^\s*(CPF|CNPJ)\s*$", re.I),
    ):
        try:
            base = page.get_by_label(lab)
            if base.count() > 0:
                el = base.first
                if el.is_visible():
                    el.fill("", timeout=2000)
                    el.fill(login, timeout=8000)
                    _log(log, "Login preenchido (rótulo / get_by_label).")
                    return True
        except Exception:
            continue

    for pat in (
        re.compile(r"cpf|cnpj|usu[aá]rio|login|e-?mail|identific", re.I),
    ):
        try:
            base = page.get_by_placeholder(pat)
            if base.count() > 0:
                el = base.first
                if el.is_visible():
                    el.fill("", timeout=2000)
                    el.fill(login, timeout=8000)
                    _log(log, "Login preenchido (placeholder).")
                    return True
        except Exception:
            continue

    # Evita pegar o primeiro text do DOM (pode ser busca/captcha): só visíveis, com dimensão.
    try:
        for sel in ('input[type="text"]', "input:not([type])"):
            box = page.locator(sel)
            n = box.count()
            for i in range(min(n, 12)):
                el = box.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    boxv = el.bounding_box()
                    if not boxv or boxv.get("width", 0) < 80:
                        continue
                    el.fill("", timeout=2000)
                    el.fill(login, timeout=8000)
                    _log(log, f"Login preenchido (heurística {sel!r}, índice {i}).")
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    return False


def _screenshot_erro(page, out_dir: Path, nome: str, log: Callable[[str], None]) -> None:
    if page is None:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        shot = out_dir / nome
        page.screenshot(path=str(shot), full_page=True)
        _log(log, f"Screenshot (erro): {shot}")
    except Exception as ex:
        _log(log, f"Aviso: não gravou screenshot ({ex}).")


def run_emitidas_playwright(
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
    Abre o navegador: por defeito **Chromium empacotado**; com ``persistent_context``/``--perfil``, **Chrome/Edge** com perfil em disco.

    Grava downloads em download_dir (ou temp). Retorna esse diretório.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError as e:
        raise RuntimeError(
            "Instale o Playwright: pip install playwright && playwright install chromium "
            "(com perfil Chrome: também «playwright install chrome»)."
        ) from e

    cfg: dict[str, Any] = dict(_cfg())
    if perfil_persistente is False:
        cfg["persistent_context"] = False
    elif perfil_persistente is True:
        cfg["persistent_context"] = True

    login_url = (cfg.get("login_url") or "https://www.nfse.gov.br/EmissorNacional/Login").strip()
    timeout_ms = int(cfg.get("timeout_ms") or 60000)
    slow_mo = int(cfg.get("slow_mo_ms") or 0)

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

    downloads_count = {"n": 0}

    def _on_download(d) -> None:
        try:
            name = d.suggested_filename or f"download_{int(time.time() * 1000)}_{downloads_count['n']}"
            downloads_count["n"] += 1
            dest = out_dir / name
            d.save_as(str(dest))
            _log(log, f"Download salvo: {dest}")
        except Exception as ex:
            _log(log, f"Aviso: não salvou download ({ex})")

    use_p, prof_dir, ch_pers = _playwright_persistent_profile(cfg, log)

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            if use_p and prof_dir is not None and ch_pers:
                prof_dir.mkdir(parents=True, exist_ok=True)
                _log(
                    log,
                    f"Playwright: perfil persistente ({ch_pers}) em {prof_dir} — "
                    "instale extensões uma vez neste perfil; feche outro navegador que use a mesma pasta.",
                )
                context = p.chromium.launch_persistent_context(
                    str(prof_dir),
                    channel=ch_pers,
                    headless=headless,
                    slow_mo=slow_mo,
                    accept_downloads=True,
                    viewport={"width": 1360, "height": 900},
                    locale="pt-BR",
                )
                context.on("download", _on_download)
                page = context.pages[0] if context.pages else context.new_page()
            else:
                _log(
                    log,
                    "Playwright: Chromium empacotado (sem perfil Chrome/Edge — sem extensões). "
                    "Para perfil persistente: NFSE_PORTAL_PLAYWRIGHT['persistent_context']=True, "
                    "browser_channel «chrome» ou «msedge», e «playwright install chrome» (ou msedge).",
                )
                lc_raw = (ch_pers or (cfg.get("browser_channel") or "").strip() or None)
                lc = None if (lc_raw and str(lc_raw).lower() == "chromium") else lc_raw
                browser = p.chromium.launch(
                    headless=headless,
                    slow_mo=slow_mo,
                    channel=lc,
                )
                context = browser.new_context(accept_downloads=True)
                context.on("download", _on_download)
                page = context.new_page()

            page.set_default_timeout(timeout_ms)
            _log(log, f"Abrindo {login_url} …")
            page.goto(login_url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=min(25000, timeout_ms))
            except Exception:
                pass
            try:
                page.wait_for_selector(
                    'input[type="password"], input[type="text"], input[type="email"]',
                    state="visible",
                    timeout=min(25000, timeout_ms),
                )
            except Exception:
                _log(log, "Aviso: formulário de login pode ainda estar a carregar (SPA).")

            filled = _tentar_preencher_login(page, login, log, user_selectors)
            if not filled:
                _screenshot_erro(page, out_dir, "portal_erro_campo_login.png", log)
                raise RuntimeError(
                    "Não foi possível localizar o campo de login (usuário/CPF/CNPJ). "
                    "Se o portal pedir Gov.br ou certificado digital, este fluxo automático não cobre — "
                    "use login por usuário/senha ou defina NFSE_PORTAL_PLAYWRIGHT['user_selectors'] em settings.py "
                    "com o seletor CSS do campo (inspecionar elemento no navegador). "
                    "Consulte portal_erro_campo_login.png na pasta de downloads da execução."
                )

            pwd_ok = False
            pwd_attempts = []
            if password_selector:
                pwd_attempts.append(password_selector)
            pwd_attempts.extend(['input[type="password"]'])
            seen = set()
            for sel in pwd_attempts:
                if not sel or sel in seen:
                    continue
                seen.add(sel)
                try:
                    base = page.locator(sel)
                    if base.count() > 0:
                        el = base.first
                        if el.is_visible():
                            el.fill(senha, timeout=15000)
                            pwd_ok = True
                            _log(log, f"Senha preenchida ({sel!r}).")
                            break
                except PlaywrightTimeout:
                    continue
                except Exception:
                    continue
            if not pwd_ok:
                _screenshot_erro(page, out_dir, "portal_erro_campo_senha.png", log)
                raise RuntimeError(
                    f"Campo de senha não encontrado ou não visível ({password_selector!r}). "
                    "Ajuste NFSE_PORTAL_PLAYWRIGHT['password_selector'] em settings ou confira se o portal "
                    "está no modo usuário/senha (não só Gov.br/certificado). Ver portal_erro_campo_senha.png."
                )

            # Entrar / Acessar / Continuar
            clicked = False
            for sel in submit_selectors:
                try:
                    if sel.startswith("role="):
                        continue
                    base = page.locator(sel)
                    if base.count() > 0:
                        el = base.first
                        if el.is_visible():
                            el.click(timeout=8000)
                            clicked = True
                            _log(log, f"Clique em enviar ({sel}).")
                            break
                except Exception:
                    continue
            if not clicked:
                for btn_name in ("Entrar", "Acessar", "Continuar", "Avançar"):
                    try:
                        page.get_by_role("button", name=re.compile(btn_name, re.I)).first.click(timeout=8000)
                        clicked = True
                        _log(log, f"Clique em botão ({btn_name}).")
                        break
                    except Exception:
                        continue
            if not clicked:
                _screenshot_erro(page, out_dir, "portal_erro_botao_entrar.png", log)
                raise RuntimeError(
                    "Botão de envio do login não encontrado (Entrar/Acessar/Continuar). "
                    "Defina NFSE_PORTAL_PLAYWRIGHT['submit_selectors'] em settings. Ver portal_erro_botao_entrar.png."
                )

            time.sleep(2)
            _log(log, "Aguardando navegação pós-login …")
            try:
                page.wait_for_load_state("networkidle", timeout=min(30000, timeout_ms))
            except Exception:
                pass

            # Tela nacional «Notas emitidas»: período da tela Django + Filtrar + XML e DANFS-e por linha.
            nav_ok = _navegar_emitidas_com_periodo(page, data_inicio, data_fim, after_emit_url, cfg, timeout_ms, log)
            cur = (page.url or "").lower()
            if not nav_ok or "emitidas" not in cur:
                _emitidas_fallback_menu_principal(page, emitidas_texts, after_emit_url, timeout_ms, log)
                if "emitidas" not in (page.url or "").lower():
                    _navegar_emitidas_com_periodo(page, data_inicio, data_fim, "", cfg, timeout_ms, log)

            _emitidas_preencher_campos_e_filtrar(page, data_inicio, data_fim, timeout_ms, log)
            max_linhas = int(cfg.get("emitidas_max_linhas") or 250)
            nproc = _emitidas_baixar_xml_e_danfs_por_linhas(page, log, max_linhas=max_linhas)
            _log(log, f"Processamento de linhas da grade: {nproc} (downloads gravados na pasta temporária).")
            time.sleep(3)

            shot = out_dir / "portal_apos_cliques.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                _log(log, f"Screenshot de referência: {shot}")
            except Exception:
                pass

            if not headless:
                if pausa_interativa:
                    _log(
                        log,
                        "Pausa: navegue no portal se precisar. Enter no terminal fecha o navegador e importa os XML da pasta.",
                    )
                    try:
                        input()
                    except EOFError:
                        pass
                else:
                    _log(log, "Aguardando até 45s por downloads automáticos…")
                    try:
                        page.wait_for_timeout(min(45000, timeout_ms))
                    except Exception:
                        pass
            else:
                try:
                    page.wait_for_timeout(12000)
                except Exception:
                    pass
        finally:
            _pw_close(context, browser, log)

    return out_dir
