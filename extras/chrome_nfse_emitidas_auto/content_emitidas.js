/* global chrome */
(function () {
  "use strict";

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function textoVisivel(el) {
    if (!el || !el.offsetParent) return false;
    const s = window.getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none";
  }

  async function esperarLinhasOuTimeout(ms) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      const rows = coletarLinhas();
      if (rows.length > 0) return rows;
      await sleep(400);
    }
    return coletarLinhas();
  }

  function coletarLinhas() {
    const specs = [
      ["table.table-striped tbody tr", true],
      ["mat-table mat-row", false],
      ["table.table-striped tbody tr", false],
      ["table tbody tr", false],
    ];
    for (const [sel, needOpcoes] of specs) {
      let list = [...document.querySelectorAll(sel)];
      if (needOpcoes) {
        list = list.filter((tr) => tr.querySelector("td.td-opcoes"));
      }
      list = list.filter(textoVisivel);
      if (list.length) return list;
    }
    return [];
  }

  function preencherDatasEfiltrar(diBr, dfBr) {
    const tryLabel = (rx) => {
      const labs = [...document.querySelectorAll("label")];
      for (const lab of labs) {
        if (!rx.test((lab.textContent || "").trim())) continue;
        const id = lab.getAttribute("for");
        let inp = id ? document.getElementById(id) : null;
        if (!inp) inp = lab.querySelector("input");
        if (inp && textoVisivel(inp)) return inp;
      }
      return null;
    };

    let elDi = tryLabel(/data\s*inicial/i);
    let elDf = tryLabel(/data\s*final/i);
    if (elDi) {
      elDi.focus();
      elDi.value = "";
      elDi.dispatchEvent(new Event("input", { bubbles: true }));
      elDi.value = diBr;
      elDi.dispatchEvent(new Event("input", { bubbles: true }));
      elDi.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (elDf) {
      elDf.focus();
      elDf.value = "";
      elDf.dispatchEvent(new Event("input", { bubbles: true }));
      elDf.value = dfBr;
      elDf.dispatchEvent(new Event("input", { bubbles: true }));
      elDf.dispatchEvent(new Event("change", { bubbles: true }));
    }

    const dts = [...document.querySelectorAll('input[type="date"]')];
    if (dts.length >= 2) {
      const p1 = diBr.split("/");
      const iso1 = p1.length === 3 ? `${p1[2]}-${p1[1].padStart(2, "0")}-${p1[0].padStart(2, "0")}` : "";
      const p2 = dfBr.split("/");
      const iso2 = p2.length === 3 ? `${p2[2]}-${p2[1].padStart(2, "0")}-${p2[0].padStart(2, "0")}` : "";
      if (iso1 && iso2) {
        dts[0].value = iso1;
        dts[1].value = iso2;
        dts[0].dispatchEvent(new Event("change", { bubbles: true }));
        dts[1].dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    const btns = [...document.querySelectorAll("button")];
    const filtrar = btns.find((b) => /filtrar/i.test(b.textContent || ""));
    if (filtrar && textoVisivel(filtrar)) {
      filtrar.click();
      return true;
    }
    return false;
  }

  function cliquePorTexto(root, rx) {
    const els = root.querySelectorAll("button, a, [role='menuitem'], .mat-mdc-menu-item");
    for (const el of els) {
      if (!textoVisivel(el)) continue;
      if (rx.test((el.textContent || "").trim())) {
        el.click();
        return true;
      }
    }
    return false;
  }

  function menuDownloadNaOverlay(rx) {
    const roots = [
      ...document.querySelectorAll(
        ".cdk-overlay-container .mat-mdc-menu-panel, .cdk-overlay-container mat-menu-panel, " +
          ".cdk-overlay-container [role='menu'], .dropdown-menu.show"
      ),
    ];
    for (const r of roots) {
      if (cliquePorTexto(r, rx)) return true;
    }
    return cliquePorTexto(document, rx);
  }

  function abrirMenuLinha(row) {
    const candidatos = [
      "td.td-opcoes .menu-suspenso-tabela button",
      "td.td-opcoes button.dropdown-toggle",
      "td.td-opcoes button",
      ".menu-suspenso-tabela button",
      "button[aria-haspopup='menu']",
      "button.mat-mdc-menu-trigger",
      "button[aria-haspopup='true']",
    ];
    for (const sel of candidatos) {
      const el = row.querySelector(sel);
      if (el && textoVisivel(el)) {
        el.click();
        return true;
      }
    }
    const bs = [...row.querySelectorAll("button")].filter(textoVisivel);
    if (bs.length) {
      bs[bs.length - 1].click();
      return true;
    }
    return false;
  }

  async function processarLinhas(maxLinhas) {
    await sleep(2000);
    let rows = await esperarLinhasOuTimeout(35000);
    if (rows.length === 0) {
      console.warn("[SF NFSe] Nenhuma linha; tente login ou período.");
      return { processadas: 0, aviso: "Sem linhas na tabela após espera." };
    }
    let ok = 0;
    const n = Math.min(rows.length, maxLinhas);
    for (let i = 0; i < n; i++) {
      const row = coletarLinhas()[i];
      if (!row) break;
      try {
        row.scrollIntoView({ block: "center", behavior: "instant" });
      } catch (_) {}
      await sleep(200);
      if (!abrirMenuLinha(row)) {
        console.warn("[SF NFSe] Menu linha", i + 1);
        continue;
      }
      await sleep(700);
      if (!menuDownloadNaOverlay(/download\s*xml/i)) {
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        continue;
      }
      await sleep(1200);
      abrirMenuLinha(row);
      await sleep(700);
      if (!menuDownloadNaOverlay(/download\s*danfs/i)) {
        menuDownloadNaOverlay(/danfs\s*-?\s*e/i);
      }
      await sleep(1200);
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      await sleep(400);
      ok++;
    }
    return { processadas: ok };
  }

  async function executar() {
    const data = await chrome.storage.session.get("sf_nfse_emitidas_auto");
    const job = data.sf_nfse_emitidas_auto;
    if (!job) return;

    await chrome.storage.session.remove("sf_nfse_emitidas_auto");

    const { diBr, dfBr, maxLinhas } = job;
    await sleep(1500);

    let rows = await esperarLinhasOuTimeout(12000);
    if (rows.length === 0) {
      preencherDatasEfiltrar(diBr, dfBr);
      await sleep(3500);
      rows = await esperarLinhasOuTimeout(25000);
    } else if (rows.length > 0) {
      preencherDatasEfiltrar(diBr, dfBr);
      await sleep(2500);
      rows = await esperarLinhasOuTimeout(15000);
    }

    const resultado = await processarLinhas(maxLinhas || 250);
    console.log("[SF NFSe] Automático concluído:", resultado);

    try {
      const div = document.createElement("div");
      div.setAttribute(
        "style",
        "position:fixed;bottom:16px;right:16px;z-index:99999;max-width:360px;padding:12px 14px;background:#0d6efd;color:#fff;border-radius:8px;font:14px/1.35 system-ui;box-shadow:0 4px 12px rgba(0,0,0,.25);"
      );
      div.textContent =
        "SaudeFinanceira: pedidos de download XML/PDF enviados para " +
        (resultado.processadas || 0) +
        " linha(s). Confira a pasta de downloads do Chrome. Depois envie os ficheiros na app local.";
      document.body.appendChild(div);
      setTimeout(() => div.remove(), 20000);
    } catch (_) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => executar().catch(console.error));
  } else {
    executar().catch(console.error);
  }
})();
