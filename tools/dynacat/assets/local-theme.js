/* Theme is a browser preference, not a config write. Dynacat 3.0 already
 * reads its theme cookie on GET and restores dynacat-theme before paint.
 * Use those native formats, avoiding POST behind a Host-rewriting proxy.
 * Keep same-origin write protection and the disabled editor untouched. */
(() => {
    if (typeof pageData === 'undefined') return;
    const storageKey = 'dynacat-theme';
    const setCookie = key => {
        document.cookie = `theme=${encodeURIComponent(key)}; Path=${pageData.baseURL || ''}/; Max-Age=63072000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
    };
    // This script runs before the module's setupPage: reconcile the native
    // cookie locally so its stale-cookie POST reconciliation is unnecessary.
    setCookie(pageData.theme);
    pageData.serverTheme = pageData.theme;
    let loading = false;
    const mark = key => {
        const choices = [...document.querySelectorAll('.theme-choices .theme-preset')];
        for (const choice of choices) choice.classList.toggle('current', choice.dataset.key === key);
        const match = choices.find(choice => choice.dataset.key === key);
        if (match) for (const preview of document.querySelectorAll('.current-theme-preview')) {
            preview.replaceChildren(match.cloneNode(true));
        }
    };
    document.addEventListener('click', async event => {
        const preset = event.target.closest?.('.theme-choices .theme-preset[data-key]');
        if (!preset) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        const key = preset.dataset.key;
        if (loading || key === pageData.theme) return;
        loading = true;
        const previous = pageData.theme;
        try {
            setCookie(key);
            // GET renders the server's validated preset CSS; never generate or
            // duplicate theme definitions, and never execute returned scripts.
            const response = await fetch(location.href, {method: 'GET', credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15000)});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const html = new DOMParser().parseFromString(await response.text(), 'text/html');
            const css = html.querySelector('#theme-style')?.textContent;
            const scheme = html.documentElement.dataset.scheme;
            if (html.documentElement.dataset.theme !== key || !css || !['light', 'dark'].includes(scheme)) {
                throw new Error('The selected theme was not returned by the dashboard');
            }
            document.querySelector('#theme-style').textContent = css;
            document.documentElement.dataset.theme = key;
            document.documentElement.dataset.scheme = scheme;
            pageData.theme = pageData.serverTheme = key;
            try { localStorage.setItem(storageKey, JSON.stringify({key, css, scheme})); } catch (_) {}
            mark(key);
        } catch (error) {
            setCookie(previous);
            alert(`Failed to set theme: ${error.message}`);
        } finally {
            loading = false;
        }
    }, true);
    // Native storage listener applies CSS/preview in other tabs. Keep its
    // cookie aligned too, without issuing a write request on the next reload.
    window.addEventListener('storage', event => {
        if (event.key !== storageKey || !event.newValue) return;
        try {
            const stored = JSON.parse(event.newValue);
            if (stored?.key && document.querySelector(`.theme-choices [data-key="${CSS.escape(stored.key)}"]`)) setCookie(stored.key);
        } catch (_) {}
    });
})();
