/* Restore disclosure state in detached incoming markup, BEFORE native layout
 * initializers can measure a temporarily collapsed document. Post-update state
 * restoration is too late: scroll-range clamping/anchoring already happened. */
export function preserveDisclosureState(previous, incoming) {
  const key = d => d.id || d.getAttribute('data-nw-disclosure') ||
    d.querySelector('summary strong')?.textContent.trim().replace(/^\d+\s+/, '') ||
    d.querySelector('summary')?.textContent.trim().replace(/^\d+\s+/, '');
  const states = new Map();
  for (const d of previous.querySelectorAll('details')) {
    const name = key(d);
    if (!states.has(name)) states.set(name, []);
    states.get(name).push(d.open);
  }
  for (const d of incoming.querySelectorAll('details')) {
    const values = states.get(key(d));
    if (values?.length) d.open = values.shift();
  }
  return incoming;
}
export function preserveWidgetState(previous, incoming) {
  if (!incoming) return incoming;
  preserveDisclosureState(previous, incoming);
  // The native header does not contain our adopted status/collapse control.
  // Prepare it off-DOM as well, rather than shrink it then rebuild a microtask later.
  if (previous.matches('.cw-merged')) {
    const header = incoming.querySelector('.widget-header');
    const status = incoming.querySelector('.widget-content .cw-status');
    if (header && status) { header.querySelector('.cw-status')?.remove(); header.append(status); }
    const button = previous.querySelector('.widget-header [data-cw-collapse-all]');
    if (header && button && !header.querySelector('[data-cw-collapse-all]')) header.append(button.cloneNode(true));
  }
  return incoming;
}
export function preserveDisclosureHTML(previous, html) {
  const template = document.createElement('template');
  // HTML is the same trusted native-renderer response consumed by Idiomorph.
  template.innerHTML = html;
  preserveWidgetState(previous, template.content.firstElementChild);
  return template.innerHTML;
}
