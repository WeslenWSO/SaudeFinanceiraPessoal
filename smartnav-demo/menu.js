/**
 * SmartNav - Menu dropdown profissional (SmartMenus-like)
 * Vanilla JS, sem jQuery
 * - Hover: delay open 120ms, delay close 250ms
 * - Teclado: Enter/Espaço abre/fecha, ESC fecha
 * - Clique fora fecha
 * - Mobile: tap abre/fecha
 */

(function () {
  'use strict';

  const OPEN_DELAY = 120;
  const CLOSE_DELAY = 250;
  const MOBILE_BREAKPOINT = 768;

  function isMobile() {
    return window.matchMedia('(max-width: ' + MOBILE_BREAKPOINT + 'px)').matches;
  }

  function init() {
    const nav = document.getElementById('smart-nav');
    if (!nav) return;

    const triggers = nav.querySelectorAll('.smart-nav-trigger');
    const dropdowns = nav.querySelectorAll('.smart-nav-dropdown');
    const menuItems = nav.querySelectorAll('.smart-nav-has-dropdown');

    let openTimer = null;
    let closeTimer = null;

    function clearTimers() {
      if (openTimer) { clearTimeout(openTimer); openTimer = null; }
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
    }

    function openDropdown(trigger, dropdown) {
      clearTimers();
      closeAll();
      dropdown.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
    }

    function closeDropdown(trigger, dropdown) {
      dropdown.classList.remove('is-open');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    }

    function closeAll() {
      triggers.forEach(function (t) { t.setAttribute('aria-expanded', 'false'); });
      dropdowns.forEach(function (d) { d.classList.remove('is-open'); });
    }

    function handleTriggerEnter(item) {
      const trigger = item.querySelector('.smart-nav-trigger');
      const dropdown = item.querySelector('.smart-nav-dropdown');
      if (!trigger || !dropdown) return;
      dropdown.classList.contains('is-open') ? closeDropdown(trigger, dropdown) : openDropdown(trigger, dropdown);
    }

    menuItems.forEach(function (item) {
      const trigger = item.querySelector('.smart-nav-trigger');
      const dropdown = item.querySelector('.smart-nav-dropdown');
      if (!trigger || !dropdown) return;

      item.addEventListener('mouseenter', function () {
        if (isMobile()) return;
        clearTimers();
        openTimer = setTimeout(function () {
          openDropdown(trigger, dropdown);
          openTimer = null;
        }, OPEN_DELAY);
      });

      item.addEventListener('mouseleave', function () {
        if (isMobile()) return;
        closeTimer = setTimeout(function () {
          closeDropdown(trigger, dropdown);
          closeTimer = null;
        }, CLOSE_DELAY);
      });

      trigger.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleTriggerEnter(item);
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          closeDropdown(trigger, dropdown);
        }
      });

      trigger.addEventListener('click', function (e) {
        if (isMobile()) {
          e.preventDefault();
          dropdown.classList.contains('is-open') ? closeDropdown(trigger, dropdown) : (closeAll(), openDropdown(trigger, dropdown));
        } else {
          e.preventDefault();
        }
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { clearTimers(); closeAll(); }
    });

    document.addEventListener('click', function (e) {
      if (!nav.contains(e.target)) { clearTimers(); closeAll(); }
    });
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
