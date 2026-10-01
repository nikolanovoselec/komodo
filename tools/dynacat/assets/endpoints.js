/* Purpose-based directory. Local filtering only; exact source URLs are unchanged. */
(() => {
  const aliases = {'/command-center':'/','/media-ops':'/media','/directory':'/endpoints-services','/news':'/endpoints-services'};
  if (aliases[location.pathname]) { location.replace(aliases[location.pathname]); return; }
  const bound = new WeakSet();
  const normalise = text => text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  const boot = () => {
    const root = document.querySelector('.es-directory-v2');
    if (!root || bound.has(root)) return;
    bound.add(root);
    const input = root.querySelector('#endpoint-search');
    const clear = root.querySelector('.es-clear');
    const groups = [...root.querySelectorAll('.es-group')];
    const domains = [...root.querySelectorAll('.es-domain')];
    const items = [...root.querySelectorAll('.es-endpoint')];
    const buttons = [...root.querySelectorAll('[data-es-category]')];
    let area = 'all';
    const filter = () => {
      const terms = normalise(input.value.trim()).split(/\s+/).filter(Boolean);
      let visible = 0;
      for (const group of groups) {
        let count = 0;
        for (const item of group.querySelectorAll('.es-endpoint')) {
          const text = normalise(item.dataset.esSearch);
          const show = (area === 'all' || area === group.dataset.esDomainKey) && terms.every(term => text.includes(term));
          item.hidden = !show;
          item.parentElement.hidden = !show;
          if (show) { count++; visible++; }
        }
        group.hidden = count === 0;
        group.querySelector('.es-group-count').textContent = String(count);
      }
      for (const domain of domains) {
        const count = [...domain.querySelectorAll('.es-endpoint')].filter(item => !item.hidden).length;
        domain.hidden = count === 0;
        domain.querySelector('.es-domain-count').textContent = String(count);
      }
      root.querySelector('.es-result-count').textContent = visible === items.length ? `${visible} links` : `${visible} of ${items.length} links`;
      root.querySelector('.es-empty').hidden = visible !== 0;
      clear.hidden = input.value.length === 0;
    };
    input.addEventListener('input', filter);
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { input.value = ''; filter(); event.stopPropagation(); }
    });
    clear.addEventListener('click', () => { input.value = ''; filter(); input.focus({preventScroll:true}); });
    for (const button of buttons) button.addEventListener('click', () => {
      area = button.dataset.esCategory;
      for (const other of buttons) other.setAttribute('aria-pressed', String(other === button));
      filter();
    });
    filter();
    root.dataset.ready = 'true';
  };
  document.addEventListener('keydown', event => {
    if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    const input = document.querySelector('.es-directory-v2 #endpoint-search');
    if (!input) return;
    event.preventDefault();
    input.focus({preventScroll:true});
  });
  document.addEventListener('construct:route', boot);
  document.addEventListener('dynacat:widget-updated', boot);
  boot();
  // Native HTML widgets hydrate after the deferred script on a cold page load.
  if (location.pathname === '/endpoints-services' && !document.querySelector('.es-directory-v2[data-ready="true"]')) {
    const observer = new MutationObserver(() => {
      boot();
      if (document.querySelector('.es-directory-v2[data-ready="true"]')) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }
})();
