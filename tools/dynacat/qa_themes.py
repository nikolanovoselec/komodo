"""Browser regression: exercise the real origin-check failure, not mock responses.
Run with dynacat-qa-venv/bin/python qa_themes.py URL OUTPUT [--staged].
Staging overrides only tracked head/assets; Origin mismatch is the observed proxy bug.
"""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent

async def main():
    url, prefix = sys.argv[1:3]
    staged = '--staged' in sys.argv
    async with async_playwright() as p:
        args = ['--no-sandbox']
        # A fulfilled staging document has no network address-space metadata;
        # Chromium otherwise blocks its LAN subresources. Test context only.
        if staged:
            args.append('--unsafely-treat-insecure-origin-as-secure=' + url.rstrip('/'))
        browser = await p.chromium.launch(headless=True, args=args)
        page = await browser.new_page(viewport={'width': 1600, 'height': 1100})
        if staged:
            await page.context.grant_permissions(['local-network-access'])
        errors, dialogs, writes = [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        async def dialog(d):
            dialogs.append(d.message)
            await d.dismiss()
        page.on('dialog', dialog)
        async def origin_mismatch(route):
            writes.append(route.request.url)
            response = await route.fetch(headers={**route.request.headers, 'origin': 'https://dynacat.novoselec.ch'})
            await route.fulfill(response=response)
        await page.route('**/api/set-theme/*', origin_mismatch)
        if staged:
            async def asset(route):
                path = ROOT / 'assets' / route.request.url.rsplit('/', 1)[-1]
                await route.fulfill(path=str(path), content_type='application/javascript')
            await page.route('**/assets/local-theme.js', asset)
            async def document(route):
                response = await route.fetch()
                text = await response.text()
                text = text.replace('</head>', '<script src="/assets/local-theme.js"></script></head>')
                await route.fulfill(response=response, body=text)
            await page.route(url.rstrip('/')+'/', document)
        await page.goto(url, wait_until='domcontentloaded')
        try:
            await page.wait_for_selector('.pve-node')
        except Exception:
            print({'errors': errors, 'text': (await page.locator('body').inner_text())[:1000]})
            raise
        initial = await page.locator('html').get_attribute('data-theme')
        report = {'initial': initial, 'themes': []}
        for theme, scheme in [('catppuccin-latte', 'light'), ('midnight-navy', 'dark'), (initial, 'dark')]:
            # An actual button click (picker is normally revealed by hover).
            button = page.locator(f'.theme-choices [data-key="{theme}"]:visible').first
            await page.locator('.header-container .theme-picker').hover()
            await button.click()
            await page.wait_for_timeout(1800)
            assert not dialogs, dialogs
            assert await page.locator('html').get_attribute('data-theme') == theme
            assert await page.locator('html').get_attribute('data-scheme') == scheme
            await page.reload(wait_until='domcontentloaded')
            await page.wait_for_selector('.pve-node')
            assert await page.locator('html').get_attribute('data-theme') == theme
            assert json.loads(await page.evaluate('localStorage.getItem("dynacat-theme")'))['key'] == theme
            await page.wait_for_timeout(2500)
            assert await page.locator('html').get_attribute('data-theme') == theme
            report['themes'].append({'key': theme, 'background': await page.locator('body').evaluate('e=>getComputedStyle(e).backgroundColor')})
            await page.screenshot(path=f'{prefix}-{theme}.png')
            if theme == 'catppuccin-latte':
                await page.evaluate("document.cookie='theme=default; Path=/'")
                await page.reload(wait_until='domcontentloaded')
                await page.wait_for_selector('.pve-node')
                assert await page.locator('html').get_attribute('data-theme') == theme
                assert 'theme=catppuccin-latte' in await page.evaluate('document.cookie')
        # A failed read must preserve the previous theme and permit another click.
        async def failed_read(route):
            await route.fulfill(status=503, body='temporarily unavailable')
        await page.route(url.rstrip('/')+'/', failed_read)
        await page.locator('.header-container .theme-picker').hover()
        await page.locator('.theme-choices [data-key="catppuccin-latte"]:visible').first.click()
        await page.wait_for_timeout(400)
        assert len(dialogs) == 1 and 'HTTP 503' in dialogs[0], dialogs
        assert await page.locator('html').get_attribute('data-theme') == initial
        await page.unroute(url.rstrip('/')+'/', failed_read)
        dialogs.clear()
        for theme in ['catppuccin-latte', initial]:
            await page.locator('.header-container .theme-picker').hover()
            await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click()
            await page.wait_for_timeout(700)
            assert await page.locator('html').get_attribute('data-theme') == theme
        report['stale_cookie_restore'] = True
        report['failure_rollback_and_retry'] = True
        assert not errors, errors
        assert not writes, writes
        report.update(errors=errors, dialogs=dialogs, theme_posts=writes)
        Path(prefix+'-report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        await browser.close()

asyncio.run(main())
