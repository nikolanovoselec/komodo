/* Local filtering for the centered launcher; link destinations stay in the JSON source. */
(() => {
  const aliases = {'/command-center':'/','/media-ops':'/media','/directory':'/endpoints-services','/news':'/endpoints-services'};
  if (aliases[location.pathname]) { location.replace(aliases[location.pathname]); return; }

  const states = new WeakMap();
  const normalise = value => String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();

  const filter = (root, state) => {
    const input = root.querySelector('#endpoint-search');
    const terms = normalise(input?.value.trim() || '').split(/\s+/).filter(Boolean);
    const links = [...root.querySelectorAll('.es-endpoint')];
    let visible = 0;
    let appCount = 0;
    let bookmarkCount = 0;

    for (const link of links) {
      const area = link.dataset.esArea || 'all';
      const text = normalise(link.dataset.esSearch || link.textContent);
      const show = (state.area === 'all' || state.area === area) && terms.every(term => text.includes(term));
      link.hidden = !show;
      if (link.closest('li')) link.closest('li').hidden = !show;
      if (show) {
        visible++;
        if (area === 'personal') bookmarkCount++;
        else appCount++;
      }
    }

    const applications = root.querySelector('.es-applications');
    const bookmarks = root.querySelector('.es-bookmarks');
    if (applications) {
      applications.hidden = appCount === 0;
      const count = applications.querySelector('.es-domain-count');
      if (count) count.textContent = String(appCount);
    }
    if (bookmarks) {
      bookmarks.hidden = bookmarkCount === 0;
      const count = bookmarks.querySelector('.es-domain-count');
      if (count) count.textContent = String(bookmarkCount);
      for (const group of bookmarks.querySelectorAll('.es-group')) {
        const groupLinks = [...group.querySelectorAll('.es-endpoint')];
        const groupCount = groupLinks.filter(link => !link.hidden).length;
        group.hidden = groupCount === 0;
        const groupCountNode = group.querySelector('.es-group-count');
        if (groupCountNode) groupCountNode.textContent = String(groupCount);
      }
    }

    const total = links.length;
    const resultCount = root.querySelector('.es-result-count');
    if (resultCount) resultCount.textContent = visible === total ? `${visible} links` : `${visible} of ${total} links`;
    const empty = root.querySelector('.es-empty');
    if (empty) empty.hidden = visible !== 0;
    const clear = root.querySelector('.es-clear');
    if (clear) clear.hidden = !input?.value;
  };

  const boot = () => {
    const root = document.querySelector('.es-directory-v2');
    if (!root || !root.querySelector('.es-app-grid')) return;
    let state = states.get(root);
    if (!state) {
      state = {area:'all'};
      root.addEventListener('input', event => {
        if (event.target instanceof Element && event.target.matches('#endpoint-search')) filter(root, state);
      });
      root.addEventListener('keydown', event => {
        if (event.target instanceof Element && event.target.matches('#endpoint-search') && event.key === 'Escape') {
          event.target.value = '';
          filter(root, state);
          event.stopPropagation();
        }
      });
      root.addEventListener('click', event => {
        if (!(event.target instanceof Element)) return;
        const clear = event.target.closest('.es-clear');
        if (clear) {
          const input = root.querySelector('#endpoint-search');
          if (input) { input.value = ''; filter(root, state); input.focus({preventScroll:true}); }
          return;
        }
        const button = event.target.closest('[data-es-category]');
        if (!button || !root.contains(button)) return;
        state.area = button.dataset.esCategory;
        for (const other of root.querySelectorAll('[data-es-category]')) {
          other.setAttribute('aria-pressed', String(other === button));
        }
        filter(root, state);
      });
      states.set(root, state);
    }
    filter(root, state);
    root.dataset.ready = 'true';
  };

  document.addEventListener('keydown', event => {
    const target = event.target instanceof Element ? event.target : null;
    if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || target?.closest('input,textarea,select,[contenteditable="true"]')) return;
    const input = document.querySelector('.es-directory-v2 #endpoint-search');
    if (!input) return;
    event.preventDefault();
    input.focus({preventScroll:true});
  });
  document.addEventListener('construct:route', boot);
  document.addEventListener('dynacat:widget-updated', boot);
  boot();
  // Native HTML widgets hydrate after the deferred script on a cold page load.
  if ((location.pathname === '/' || location.pathname === '/endpoints-services') && !document.querySelector('.es-directory-v2[data-ready="true"]')) {
    const observer = new MutationObserver(() => {
      boot();
      if (document.querySelector('.es-directory-v2[data-ready="true"]')) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }
})();
