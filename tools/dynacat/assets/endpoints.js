/* Keep legacy routes and mark the native HTML widget ready when Dynacat hydrates it. */
(() => {
  const aliases = {
    '/command-center':'/',
    '/media-ops':'/media',
    '/directory':'/endpoints-services',
    '/news':'/endpoints-services'
  };
  if (aliases[location.pathname]) {
    location.replace(aliases[location.pathname]);
    return;
  }

  const boot = () => {
    const root = document.querySelector('.es-directory-v2');
    if (root?.querySelector('.es-app-grid')) root.dataset.ready = 'true';
  };

  document.addEventListener('construct:route', boot);
  document.addEventListener('dynacat:widget-updated', boot);
  boot();

  if ((location.pathname === '/' || location.pathname === '/endpoints-services') &&
      !document.querySelector('.es-directory-v2[data-ready="true"]')) {
    const observer = new MutationObserver(() => {
      boot();
      if (document.querySelector('.es-directory-v2[data-ready="true"]')) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }
})();
