(() => {
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
      if (url) window.location.assign(url);
      return { focus() {} };
    };
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
})();
