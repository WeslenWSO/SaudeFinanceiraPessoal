(function () {
  'use strict';

  var OVERLAY_ID = 'app-filtro-loading';

  function getOverlay() {
    var el = document.getElementById(OVERLAY_ID);
    if (el) {
      return el;
    }
    el = document.createElement('div');
    el.id = OVERLAY_ID;
    el.className = 'app-filtro-loading';
    el.setAttribute('hidden', '');
    el.setAttribute('aria-live', 'polite');
    el.setAttribute('aria-busy', 'true');
    el.innerHTML =
      '<div class="app-filtro-loading-box">' +
      '<i class="fas fa-hourglass-half fa-spin fa-3x" aria-hidden="true"></i>' +
      '<p class="mb-0">Carregando…</p>' +
      '</div>';
    document.body.appendChild(el);
    return el;
  }

  function showLoading(customMessage) {
    var overlay = getOverlay();
    overlay.removeAttribute('hidden');
    document.body.style.cursor = 'wait';
    var msgEl = overlay.querySelector('.app-filtro-loading-box p');
    if (msgEl) {
      msgEl.textContent = customMessage || 'Carregando…';
    }
  }

  window.showFiltroLoading = showLoading;
  window.hideFiltroLoading = hideLoading;

  function hideLoading() {
    var overlay = document.getElementById(OVERLAY_ID);
    if (overlay) {
      overlay.setAttribute('hidden', '');
    }
    document.body.style.cursor = '';
  }

  function shouldShowForForm(form) {
    if (!form || form.tagName !== 'FORM') {
      return false;
    }
    if (form.hasAttribute('data-no-loading')) {
      return false;
    }
    if (form.dataset.loading === 'true' || form.classList.contains('form-com-loading')) {
      return true;
    }
    var method = (form.getAttribute('method') || 'get').toLowerCase();
    if (method !== 'get') {
      return false;
    }
    if ((form.getAttribute('target') || '').toLowerCase() === '_blank') {
      return false;
    }
    return true;
  }

  function shouldShowForLink(link) {
    if (!link || link.tagName !== 'A') {
      return false;
    }
    if (link.hasAttribute('data-no-loading')) {
      return false;
    }
    if (link.target === '_blank' || link.hasAttribute('download')) {
      return false;
    }
    var href = link.getAttribute('href') || '';
    if (!href || href.charAt(0) === '#') {
      return false;
    }
    if (link.closest('.pagination')) {
      return true;
    }
    if (link.classList.contains('filtro-link') || link.dataset.loading === 'true') {
      return true;
    }
    return false;
  }

  document.addEventListener(
    'submit',
    function (event) {
      var form = event.target;
      if (shouldShowForForm(form)) {
        var msg = (form && form.dataset && form.dataset.loadingMessage) || '';
        showLoading(msg || undefined);
      }
    },
    true
  );

  document.addEventListener(
    'click',
    function (event) {
      var link = event.target.closest('a');
      if (link && shouldShowForLink(link)) {
        showLoading();
      }
    },
    true
  );

  window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
      hideLoading();
    }
  });

  window.addEventListener('load', hideLoading);
})();
