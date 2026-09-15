/* Native Dynacat 3.0 updates replace widget content. Preserve only this
 * dashboard's disclosure/keyboard state through its public completion event.
 * No polling added: native polling pauses hidden pages and avoids overlap. */
(() => {
    // Dynacat 3.0 compares widget position across an asynchronous fetch. Touch
    // momentum continues after touchmove, so its correction can undo a fling.
    // Suppress ONLY its same-task post-update scrollBy while the viewport moves;
    // keep normal scroll APIs, idle layout anchoring and native 1s polling intact.
    const nativeScrollBy = window.scrollBy.bind(window);
    let movingUntil = 0, completingUpdate = false;
    window.addEventListener('scroll', () => { movingUntil = performance.now() + 250; }, {passive:true});
    document.addEventListener('dynacat:widget-updated', event => {
        if (!event.detail?.widget?.matches('.komodo-widget,.media-ops-widget')) return;
        completingUpdate = true;
        queueMicrotask(() => { completingUpdate = false; });
    });
    window.scrollBy = function(...args) {
        if (completingUpdate && performance.now() < movingUntil && args[0]?.behavior === 'auto') return;
        return nativeScrollBy(...args);
    };
    const header = document.querySelector('.header-container .header');
    if (header && !header.querySelector('.cc-page-select')) {
        const select = document.createElement('select');
        select.className = 'cc-page-select';
        select.setAttribute('aria-label', 'Navigate pages');
        for (const [path, label] of [['/hardware-workloads','HARDWARE & WORKLOADS'],['/networking','NETWORKING'],['/media','MEDIA'],['/endpoints-services','ENDPOINTS & SERVICES']]) {
            select.add(new Option(label, path, false, location.pathname === path || (location.pathname === '/' && path === '/hardware-workloads')));
        }
        select.addEventListener('change', () => { location.assign(select.value); });
        header.append(select);
        window.addEventListener('pageshow', () => { select.value = location.pathname === '/' ? '/hardware-workloads' : location.pathname; });
    }
    const opened = new Map();
    let focused = null;
    const detailKey = d => d.querySelector('summary strong')?.textContent.trim().replace(/^\d+\s+/, '');
    document.addEventListener('toggle', event => {
        const d = event.target;
        if (!(d instanceof HTMLDetailsElement) || !d.isConnected) return;
        const widget = d.closest('.komodo-widget');
        if (!widget) return;
        const key = widget.dataset.widgetId;
        if (!opened.has(key)) opened.set(key, new Set());
        if (d.open) opened.get(key).add(detailKey(d));
        else opened.get(key).delete(detailKey(d));
    }, true);
    document.addEventListener('focusin', event => {
        const element = event.target;
        const widget = element.closest('.komodo-widget');
        focused = widget && element.matches('a[href],summary') ? {
            element, widget: widget.dataset.widgetId,
            href: element.getAttribute('href'),
            summary: element.matches('summary') ? detailKey(element.parentElement) : null,
        } : null;
    });
    document.addEventListener('dynacat:widget-updated', event => {
        const widget = event.detail?.widget;
        if (!widget?.matches('.komodo-widget')) return;
        const keys = opened.get(widget.dataset.widgetId);
        for (const d of widget.querySelectorAll('details')) d.open = !!keys?.has(detailKey(d));
        if (focused?.widget !== widget.dataset.widgetId || focused.element.isConnected || document.activeElement !== document.body) return;
        const replacement = focused.href
            ? [...widget.querySelectorAll('a[href]')].find(a => a.getAttribute('href') === focused.href)
            : [...widget.querySelectorAll('details')].find(d => detailKey(d) === focused.summary)?.querySelector('summary');
        replacement?.focus({preventScroll:true});
    });
})();
