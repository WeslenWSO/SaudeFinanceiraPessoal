/**
 * SmartNav — desktop hover + mobile/tablet drawer estilo app
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
    const backdrop = document.getElementById('smart-nav-backdrop');
    const menu = document.getElementById('smart-nav-menu');

    nav.classList.remove('is-mobile-open');
    document.body.classList.remove('smart-nav-drawer-open');
    if (toggler) {
      toggler.setAttribute('aria-expanded', 'false');
      toggler.setAttribute('aria-label', 'Abrir menu');
    }
    if (backdrop) {
      backdrop.hidden = true;
    }

    const triggers = nav.querySelectorAll('.smart-nav-trigger');
    const dropdowns = nav.querySelectorAll('.smart-nav-dropdown');
    const menuItems = nav.querySelectorAll('.smart-nav-has-dropdown');

    function setMobileOpen(open) {
      var icon = toggler ? toggler.querySelector('.smart-nav-toggler-fa') : null;
      if (open) {
        nav.classList.add('is-mobile-open');
        document.body.classList.add('smart-nav-drawer-open');
        if (toggler) {
          toggler.setAttribute('aria-expanded', 'true');
          toggler.setAttribute('aria-label', 'Fechar menu');
        }
        if (icon) {
          icon.classList.remove('fa-bars');
          icon.classList.add('fa-times');
        }
        if (backdrop) backdrop.hidden = false;
      } else {
        nav.classList.remove('is-mobile-open');
        document.body.classList.remove('smart-nav-drawer-open');
        if (toggler) {
          toggler.setAttribute('aria-expanded', 'false');
          toggler.setAttribute('aria-label', 'Abrir menu');
        }
        if (icon) {
          icon.classList.remove('fa-times');
          icon.classList.add('fa-bars');
        }
        if (backdrop) backdrop.hidden = true;
        closeAll();
      }
    }

    function isMobileOpen() {
      return nav.classList.contains('is-mobile-open');
    }

    var togglerHandledByTouch = false;
    function handleTogglerTap() {
      if (!isMobile()) return;
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
        if (!isMobile()) return;
        e.preventDefault();
        togglerHandledByTouch = true;
        handleTogglerTap();
      }, { passive: false });
    }

    if (backdrop) {
      backdrop.addEventListener('click', function () {
        if (isMobile() && isMobileOpen()) setMobileOpen(false);
      });
      backdrop.addEventListener('touchend', function (e) {
        e.preventDefault();
        if (isMobile() && isMobileOpen()) setMobileOpen(false);
      }, { passive: false });
    }

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
      // No mobile permite vários? Fecha outros para focar um
      closeAll();
      dropdown.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      currentOpen = { trigger: trigger, dropdown: dropdown };
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
        e.preventDefault();
        if (isMobile()) {
          if (dropdown.classList.contains('is-open')) {
            closeDropdown(trigger, dropdown);
          } else {
            closeAll();
            openDropdown(trigger, dropdown);
          }
        }
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        clearTimers();
        closeAll();
        if (isMobile() && isMobileOpen()) {
          setMobileOpen(false);
        }
      }
    });

    document.addEventListener('click', function (e) {
      if (!nav.contains(e.target) && !(backdrop && backdrop.contains(e.target))) {
        clearTimers();
        closeAll();
      }
    });

    // Fechar drawer ao navegar
    if (menu) {
      menu.querySelectorAll('a.smart-nav-link, a.smart-nav-trigger-link').forEach(function (link) {
        link.addEventListener('click', function () {
          if (isMobile() && isMobileOpen()) {
            setMobileOpen(false);
          }
        });
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
