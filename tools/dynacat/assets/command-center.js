/* Native Dynacat 3.0 updates replace widget content. Preserve only this
 * dashboard's disclosure/keyboard state through its public completion event.
 * No polling added: native polling pauses hidden pages and avoids overlap. */
(() => {
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
