"""Live compact-card regression. Pass URL OUTPUT; --baseline records old bounds."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url, prefix = sys.argv[1:3]
    baseline = '--baseline' in sys.argv
    report = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--no-sandbox'])
        for width, height in [(1600, 1100), (1024, 900), (768, 1024), (390, 844)]:
            page = await browser.new_page(viewport={'width': width, 'height': height})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_selector('.pve-node')
            for theme in ['midnight-navy', 'catppuccin-latte']:
                # Exercise the desktop picker, then assess the responsive view.
                await page.set_viewport_size({'width': 1600, 'height': 1100})
                picker = page.locator('.header-container .theme-picker')
                await picker.hover()
                await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click()
                await page.set_viewport_size({'width': width, 'height': height})
                await page.locator('.pve-heading').click()
                await page.keyboard.press('Escape')
                await page.mouse.move(0, 0)
                await page.reload(wait_until='domcontentloaded')
                await page.wait_for_selector('.pve-node')
                await page.evaluate('window.scrollTo(0, 0)')
                await page.wait_for_timeout(1500)
                assert await page.locator('html').get_attribute('data-theme') == theme
                sizes = await page.evaluate('''() => Object.fromEntries(
                    ['.pve-node','.pve-guests .k-host'].map(s => [s,
                    [...document.querySelectorAll(s)].map(e => {
                        const b=e.getBoundingClientRect();return {width:b.width,height:b.height};
                    })]))''')
                rail = await page.locator('.page-column:has(.cc-rail-clock)').bounding_box()
                resource = await page.locator('.pve-resources').bounding_box()
                clock = await page.locator('.cc-rail-clock').bounding_box()
                weather = await page.locator('.cc-rail-weather').bounding_box()
                renovate = await page.locator('.renovate-prs').bounding_box()
                assert await page.locator('.page-columns > .page-column').count() == 2
                assert await page.locator('.cc-top-clock,.cc-top-weather').count() == 0
                assert clock['y']+clock['height'] <= weather['y']
                assert weather['y']+weather['height'] <= renovate['y']
                assert clock['x'] == weather['x'] == renovate['x']
                assert clock['width'] == weather['width'] == renovate['width'] == rail['width']
                if width == 1600:
                    assert rail['width'] == 286
                    assert abs(resource['y']-rail['y']) < 1
                    assert rail['x'] >= resource['x']+resource['width']
                    assert len(set(await page.locator('.pve-node').evaluate_all('es=>es.map(e=>e.getBoundingClientRect().y)'))) == 1
                else:
                    assert rail['y'] > resource['y']+resource['height']
                assert await page.locator('.cc-rail-clock [data-time-in-zone]').count() == 2
                assert await page.locator('.cc-rail-clock [data-date]').inner_text()
                assert 'Bern' in await page.locator('.cc-rail-weather').inner_text()
                assert await page.locator('.cc-rail-clock,.cc-rail-weather').evaluate_all('es=>es.every(e=>e.scrollWidth<=e.clientWidth)')
                await page.locator('.page-column:has(.cc-rail-clock)').screenshot(path=f'{prefix}-{width}-{theme}-rail.png')
                await page.evaluate('window.scrollTo(0,0)')
                sizes['rail'] = [rail]
                sizes['resources'] = [resource]
                assert len(sizes['.pve-node']) == 3
                assert len(sizes['.pve-guests .k-host']) == 9
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
                assert await page.locator('.pve-rx').count() >= 3
                assert await page.locator('.pve-tx').count() >= 3
                labels = await page.locator('.pve-guest-source').all_text_contents()
                assert sum('RAM Komodo' in x and 'disk Komodo' in x for x in labels) == 6
                assert sum('RAM PVE' in x and 'disk PVE' in x for x in labels) == 3
                assert 'rootfs' not in (await page.locator('.pve-resources').inner_text()).lower()
                await page.screenshot(path=f'{prefix}-{width}-{theme}.png', full_page=True)
                await page.screenshot(path=f'{prefix}-{width}-{theme}-viewport.png')
                await page.locator('.pve-node').first.screenshot(path=f'{prefix}-{width}-{theme}-node.png')
                await page.locator('.pve-guests').screenshot(path=f'{prefix}-{width}-{theme}-guests.png')
                await page.evaluate('window.scrollTo(0, 0)')
                assert await page.locator('.pve-node header strong').all_text_contents() == ['proxmox-i', 'proxmox-ii', 'proxmox-iii']
                assert await page.evaluate('document.querySelector(".workload-attention").compareDocumentPosition(document.querySelector(".top-consumers")) & Node.DOCUMENT_POSITION_FOLLOWING')
                report[f'{width}-{theme}'] = sizes
                if not baseline:
                    assert await page.locator('.pve-node').evaluate_all('''nodes => nodes.every(n => {
                        const [cpu,ram,zfs,net] = ['.pve-cpu','.pve-capacities','.pve-zfs','.pve-network'].map(s => n.querySelector(s).getBoundingClientRect());
                        return Math.abs(cpu.y-ram.y)<1 && Math.abs(ram.y-zfs.y)<1 && cpu.right<=ram.x && ram.right<=zfs.x && net.width>cpu.width*2.5;
                    })'''), 'Resource columns or network span changed'
                    assert max(x['height'] for x in sizes['.pve-node']) <= 330, sizes
                    assert max(x['height'] for x in sizes['.pve-guests .k-host']) <= (82 if width == 390 else 58), sizes
                    rows = await page.locator('.pve-guests .k-host').evaluate_all('es=>es.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,w:e.getBoundingClientRect().width,metricX:e.querySelector(".k-metrics").getBoundingClientRect().x}))')
                    assert len({r['x'] for r in rows}) == 1 and len({r['w'] for r in rows}) == 1, rows
                    assert len({r['metricX'] for r in rows}) == 1, rows
                    assert all(b['y']>a['y'] for a,b in zip(rows,rows[1:])), rows
                    assert min(x['height'] for x in sizes['.pve-guests .k-host']) >= 44
                    assert await page.locator('.pve-guests .k-host meter').count() == 27
                    assert await page.locator('.pve-guests .pve-guest-meta').count() == 9
                    assert await page.locator('.pve-guests .pve-guest-source').evaluate_all('es => es.every(e => parseFloat(getComputedStyle(e).fontSize) >= 10 && e.scrollWidth <= e.clientWidth)')
                    assert await page.locator('.pve-guests .k-host').evaluate_all('es => es.every(e => e.scrollWidth <= e.clientWidth && e.querySelector("header strong").textContent.trim() && e.querySelector(".pve-guest-meta").textContent.includes("#"))')
                    assert await page.locator('.pve-stopped .cc-resource-link').count() == 10
                    assert await page.locator('.pve-stopped summary').evaluate('e=>e.getBoundingClientRect().height>=44')
            assert not errors, errors
            await page.close()
        await browser.close()
    Path(prefix+'-bounds.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({view: {selector: {'count': len(bounds), 'max_height': max(b['height'] for b in bounds)} for selector, bounds in sizes.items()} for view, sizes in report.items()}, indent=2))

asyncio.run(main())
