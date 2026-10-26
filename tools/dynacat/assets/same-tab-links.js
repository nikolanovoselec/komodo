(() => {
  const preserveLauncherScroll = window.location.pathname.replace(/\/+$/, '') === '/endpoints-services';
  const scrollStorageKey = `__dynacatScrollY:${window.location.pathname}${window.location.search}${window.location.hash}`;
  const canPersistScroll = (() => {
    if (!preserveLauncherScroll) return false;
    const probeKey = `${scrollStorageKey}:probe`;
    try {
      sessionStorage.setItem(probeKey, '1');
      sessionStorage.removeItem(probeKey);
      return true;
    } catch {
      return false;
    }
  })();
  const useNativeScrollRestoration = () => {
    try { history.scrollRestoration = 'auto'; } catch {}
  };
  const saveScrollPosition = () => {
    if (!canPersistScroll) return false;
    try {
      sessionStorage.setItem(scrollStorageKey, String(window.scrollY));
      return true;
    } catch {
      useNativeScrollRestoration();
      return false;
    }
  };
  const saveBeforeExternalLink = (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    try {
      if (new URL(link.href, window.location.href).origin !== window.location.origin) {
        saveScrollPosition();
        setTimeout(() => {
          if (event.defaultPrevented) {
            try { sessionStorage.removeItem(scrollStorageKey); } catch {}
            useNativeScrollRestoration();
          }
        }, 0);
      }
    } catch {}
  };
  const restoreScrollPosition = (event) => {
    if (!canPersistScroll) return;
    let stored;
    try {
      stored = sessionStorage.getItem(scrollStorageKey);
    } catch {
      useNativeScrollRestoration();
      return;
    }
    const navigationType = performance.getEntriesByType?.('navigation')?.[0]?.type;
    const isReturn = event.persisted || navigationType === 'back_forward' || navigationType === 'reload';
    if (!isReturn) {
      if (stored !== null) {
        try { sessionStorage.removeItem(scrollStorageKey); } catch { useNativeScrollRestoration(); }
      }
      return;
    }
    if (stored === null) {
      useNativeScrollRestoration();
      return;
    }
    const saved = Number(stored);
    try {
      sessionStorage.removeItem(scrollStorageKey);
    } catch {
      useNativeScrollRestoration();
      return;
    }
    if (!Number.isFinite(saved) || saved < 0) {
      useNativeScrollRestoration();
      return;
    }
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({
      left: window.scrollX,
      top: saved,
      behavior: 'instant',
    })));
  };

  if (preserveLauncherScroll) {
    document.addEventListener('click', saveBeforeExternalLink, true);
    window.addEventListener('pageshow', restoreScrollPosition);
  }

  const normalizeLinks = () => {
    document.querySelectorAll('a[target="_blank"]').forEach((link) => {
      link.removeAttribute('target');
    });
  };

  const install = () => {
    normalizeLinks();
    new MutationObserver(normalizeLinks).observe(document.documentElement, {
      childList: true,
      subtree: true,
    });

    window.open = (url) => {
      if (url) {
        saveScrollPosition();
        window.location.assign(url);
      }
      return { focus() {} };
    };
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
})();
