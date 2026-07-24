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
  const MOBILE_BREAKPOINT = 991;

  function isMobile() {
    return window.matchMedia('(max-width: ' + MOBILE_BREAKPOINT + 'px)').matches;
  }

  function init() {
    const nav = document.getElementById('smart-nav');
    if (!nav) return;

    const toggler = document.getElementById('smart-nav-toggler');
    // Mobile: menu sempre começa retraído; desktop: sem efeito
    nav.classList.remove('is-mobile-open');
    if (toggler) {
      toggler.setAttribute('aria-expanded', 'false');
      toggler.setAttribute('aria-label', 'Abrir menu');
    }

    // Ao carregar a página: se for mobile, garantir menu fechado (evita flash aberto)
    if (isMobile()) {
      nav.classList.remove('is-mobile-open');
    }

    const triggers = nav.querySelectorAll('.smart-nav-trigger');
    const dropdowns = nav.querySelectorAll('.smart-nav-dropdown');
    const menuItems = nav.querySelectorAll('.smart-nav-has-dropdown');

    function setMobileOpen(open) {
      if (open) {
        nav.classList.add('is-mobile-open');
        if (toggler) {
          toggler.setAttribute('aria-expanded', 'true');
          toggler.setAttribute('aria-label', 'Fechar menu');
        }
      } else {
        nav.classList.remove('is-mobile-open');
        if (toggler) {
          toggler.setAttribute('aria-expanded', 'false');
          toggler.setAttribute('aria-label', 'Abrir menu');
        }
        closeAll();
      }
    }

    function isMobileOpen() {
      return nav.classList.contains('is-mobile-open');
    }

    var togglerHandledByTouch = false;
    function handleTogglerTap() {
      setMobileOpen(!isMobileOpen());
    }

    if (toggler) {
      toggler.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (togglerHandledByTouch) {
          togglerHandledByTouch = false;
          return;
        }
        handleTogglerTap();
      });
      toggler.addEventListener('touchend', function (e) {
        e.preventDefault();
        togglerHandledByTouch = true;
        handleTogglerTap();
      }, { passive: false });
    }

    // Ao redimensionar para desktop, fechar o menu para não ficar fixo
    window.addEventListener('resize', function () {
      if (!isMobile() && isMobileOpen()) {
        setMobileOpen(false);
      }
    });

    let openTimer = null;
    let closeTimer = null;
    let currentOpen = null;

    function clearTimers() {
      if (openTimer) {
        clearTimeout(openTimer);
        openTimer = null;
      }
      if (closeTimer) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
    }

    function openDropdown(trigger, dropdown) {
      clearTimers();
      closeAll();
      dropdown.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      currentOpen = { trigger, dropdown };
    }

    function closeDropdown(trigger, dropdown) {
      dropdown.classList.remove('is-open');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
      if (currentOpen && currentOpen.dropdown === dropdown) {
        currentOpen = null;
      }
    }

    function closeAll() {
      triggers.forEach(function (t) {
        t.setAttribute('aria-expanded', 'false');
      });
      dropdowns.forEach(function (d) {
        d.classList.remove('is-open');
      });
      currentOpen = null;
    }

    function handleTriggerEnter(item) {
      const trigger = item.querySelector('.smart-nav-trigger');
      const dropdown = item.querySelector('.smart-nav-dropdown');
      if (!trigger || !dropdown) return;

      if (dropdown.classList.contains('is-open')) {
        closeDropdown(trigger, dropdown);
      } else {
        openDropdown(trigger, dropdown);
      }
    }

    function handleTriggerLeave(item) {
      if (isMobile()) return;
      const trigger = item.querySelector('.smart-nav-trigger');
      const dropdown = item.querySelector('.smart-nav-dropdown');
      if (!dropdown) return;

      closeTimer = setTimeout(function () {
        closeDropdown(trigger, dropdown);
        closeTimer = null;
      }, CLOSE_DELAY);
    }

    function handleDropdownEnter(item) {
      if (isMobile()) return;
      clearTimers();
    }

    function handleDropdownLeave(item) {
      if (isMobile()) return;
      const trigger = item.querySelector('.smart-nav-trigger');
      const dropdown = item.querySelector('.smart-nav-dropdown');
      handleTriggerLeave(item);
    }

    // Eventos por item (trigger + dropdown)
    menuItems.forEach(function (item) {
      const trigger = item.querySelector('.smart-nav-trigger');
      const dropdown = item.querySelector('.smart-nav-dropdown');
      if (!trigger || !dropdown) return;

      // Mouse enter no item (trigger ou dropdown) - abrir após delay
      item.addEventListener('mouseenter', function () {
        if (isMobile()) return;
        clearTimers();
        openTimer = setTimeout(function () {
          openDropdown(trigger, dropdown);
          openTimer = null;
        }, OPEN_DELAY);
      });

      // Mouse leave no item - fechar após delay
      item.addEventListener('mouseleave', function () {
        if (isMobile()) return;
        closeTimer = setTimeout(function () {
          closeDropdown(trigger, dropdown);
          closeTimer = null;
        }, CLOSE_DELAY);
      });

      // Teclado: Enter / Espaço no trigger
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

      // Clique: desktop = preventDefault (não navega), mobile = toggle
      trigger.addEventListener('click', function (e) {
        if (isMobile()) {
          e.preventDefault();
          if (dropdown.classList.contains('is-open')) {
            closeDropdown(trigger, dropdown);
          } else {
            closeAll();
            openDropdown(trigger, dropdown);
          }
        } else {
          e.preventDefault();
        }
      });
    });

    // ESC fecha qualquer dropdown e, no mobile, o painel do menu
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        clearTimers();
        closeAll();
        if (isMobile() && isMobileOpen()) {
          setMobileOpen(false);
        }
      }
    });

    // Clique fora fecha dropdowns e, no mobile, o painel do menu
    document.addEventListener('click', function (e) {
      if (!nav.contains(e.target)) {
        clearTimers();
        closeAll();
        if (isMobile() && isMobileOpen()) {
          setMobileOpen(false);
        }
      }
    });

    // Fechar menu mobile ao clicar em um link (navegação)
    nav.querySelectorAll('.smart-nav-link').forEach(function (link) {
      link.addEventListener('click', function () {
        if (isMobile() && isMobileOpen()) {
          setMobileOpen(false);
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
