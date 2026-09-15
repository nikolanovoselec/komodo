/* Media-only interaction state; native Dynacat owns all polling. */
(() => {
  const state = new Map();
  let focus = null;
  const widgetFor = el => el?.closest?.('.media-ops-widget');
  document.addEventListener('toggle', event => {
    const d = event.target, w = widgetFor(d);
    if (!w || !(d instanceof HTMLDetailsElement) || !d.isConnected) return;
    const key = w.dataset.widgetId;
    state.set(key, {open:d.open, scroll:d.scrollTop});
  }, true);
  document.addEventListener('scroll', event => {
    const d = event.target, w = widgetFor(d);
    if (w && d.matches?.('details')) state.set(w.dataset.widgetId, {open:d.open,scroll:d.scrollTop});
  }, true);
  document.addEventListener('focusin', event => {
    const el = event.target, w = widgetFor(el);
    focus = w && el.matches('a,summary') ? {el, widget:w.dataset.widgetId,
      index:[...w.querySelectorAll('a,summary')].indexOf(el), href:el.getAttribute('href')} : null;
  });
  document.addEventListener('dynacat:widget-updated', event => {
    const w = event.detail?.widget;
    if (!w?.matches('.media-ops-widget')) return;
    const saved = state.get(w.dataset.widgetId);
    const d = w.querySelector('details');
    if (d && saved) {d.open=saved.open;d.scrollTop=saved.scroll;}
    if (focus?.widget !== w.dataset.widgetId || focus.el.isConnected || document.activeElement !== document.body) return;
    const el = w.querySelectorAll('a,summary')[focus.index];
    if (el && el.getAttribute('href') === focus.href) el.focus({preventScroll:true});
  });
})();
