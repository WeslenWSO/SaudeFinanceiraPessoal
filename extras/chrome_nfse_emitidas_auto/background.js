/**
 * Mensagens externas apenas de http://127.0.0.1 ou http://localhost (externally_connectable).
 */
function isoParaBR(iso) {
  if (!iso || iso.length < 10) return "";
  const p = iso.slice(0, 10).split("-");
  if (p.length !== 3) return iso;
  return `${p[2]}/${p[1]}/${p[0]}`;
}

chrome.runtime.onMessageExternal.addListener((request, sender, sendResponse) => {
  const origin = sender.origin || "";
  if (
    !origin.startsWith("http://127.0.0.1") &&
    !origin.startsWith("http://localhost")
  ) {
    sendResponse({ ok: false, error: "Origem não autorizada." });
    return;
  }
  if (request.action !== "sf_nfse_emitidas_auto") {
    sendResponse({ ok: false, error: "Ação inválida." });
    return;
  }
  const diIso = (request.diIso || "").trim();
  const dfIso = (request.dfIso || "").trim();
  if (!diIso || !dfIso) {
    sendResponse({ ok: false, error: "Datas ISO em falta." });
    return;
  }
  const maxLinhas = Math.min(Math.max(Number(request.maxLinhas) || 250, 1), 500);
  const diBr = isoParaBR(diIso);
  const dfBr = isoParaBR(dfIso);
  const base = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas";
  const qs = new URLSearchParams({ datainicio: diBr, datafim: dfBr });
  const url = `${base}?${qs.toString()}`;

  chrome.storage.session
    .set({
      sf_nfse_emitidas_auto: {
        diIso,
        dfIso,
        diBr,
        dfBr,
        maxLinhas,
        startedAt: Date.now(),
      },
    })
    .then(() => chrome.tabs.create({ url }))
    .then(() => {
      sendResponse({
        ok: true,
        message:
          "Nova guia aberta no portal. Mantenha sessão iniciada; o script corre quando a página carregar.",
      });
    })
    .catch((e) => {
      sendResponse({ ok: false, error: String(e && e.message ? e.message : e) });
    });
  return true;
});
