"""Read-only live baseline / browser-routed candidate workload verification."""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parent
MEASURE = '''() => {const w=document.querySelector('.cw-merged'),row=w.querySelector('.cw-workload:has(.cw-docker[open])')||w.querySelector('.cw-workload'),m=row.querySelector('.k-metrics'),h=w.querySelector('.pve-matrix-head>div');const rect=e=>({x:e.getBoundingClientRect().x,width:e.getBoundingClientRect().width});return {viewport:innerWidth,row:rect(row),metrics:rect(m),grid:getComputedStyle(m).gridTemplateColumns,headerGrid:getComputedStyle(h).gridTemplateColumns,columns:[...m.children].map(rect),headers:[...h.children].map(rect),docker:rect(row.querySelector('.cw-docker')),overflow:document.documentElement.scrollWidth>innerWidth}}'''
async def main():
    base, dest, mode=sys.argv[1:4];out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1600,'height':1100})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        if mode=='candidate':
            async def asset(route):
                name=route.request.url.split('/')[-1].split('?')[0]
                await route.fulfill(path=str(ROOT/'assets'/name))
            await page.route('**/assets/workload-docker.*',asset)
        await page.goto(base+'/hardware-workloads');await page.wait_for_selector('.cw-workload')
        await page.evaluate("window.workloadUpdates=[];document.addEventListener('dynacat:widget-updated',e=>{if(e.detail.widget.matches('.cw-merged'))workloadUpdates.push(performance.now())})")
        if mode=='candidate':
            # Template-only deletion mirrored on real responses, not fixture data.
            await page.evaluate('''() => {const clean=()=>document.querySelectorAll('.cw-merged .cw-docker-stats,.cw-merged .cw-collapse-bar,.cw-merged .cw-hide-hint').forEach(e=>e.remove());clean();document.addEventListener('dynacat:widget-updated',clean)}''')
        measurements=[];cadence=[]
        for theme in ['midnight-navy','catppuccin-latte']:
            await page.locator('.header-container .theme-picker').hover()
            await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click()
            for width in [1600,1024,390]:
                await page.set_viewport_size({'width':width,'height':1100 if width>500 else 844})
                await page.wait_for_timeout(300)
                measurement=await page.evaluate(MEASURE);measurement['theme']=theme;measurements.append(measurement)
                await page.locator('.cw-merged').screenshot(path=str(out/f'{mode}-{theme}-{width}.png'))
                if mode!='baseline':
                    assert await page.locator('.cw-overview').evaluate("e=>getComputedStyle(e).justifyContent==='flex-end' && getComputedStyle(e).textAlign==='right'"),'Workload totals must align right'
                    detail=page.locator('.cw-docker').filter(has=page.locator('.cw-container')).first
                    await detail.locator('summary').click();await page.wait_for_timeout(100)
                    assert await page.locator('[data-cw-collapse-all]').is_visible()
                    if width==390:
                        assert await page.locator('.cw-merged>.widget-header').evaluate('''h=>{const s=h.querySelector('.cw-status').getBoundingClientRect(),b=h.querySelector('button').getBoundingClientRect();return Math.abs((s.y+s.height/2)-(b.y+b.height/2))<2}'''),'Mobile action is not alongside issue summary'
                    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    await page.locator('.cw-merged').screenshot(path=str(out/f'{mode}-{theme}-{width}-expanded.png'))
                    await page.locator('[data-cw-collapse-all]').click();await page.wait_for_timeout(100)
        (out/f'{mode}-measurements.json').write_text(json.dumps(measurements,indent=2))
        if mode!='baseline':
            await page.set_viewport_size({'width':1600,'height':1100})
            disclosures=page.locator('.cw-docker').filter(has=page.locator('.cw-container'))
            button=page.locator('.cw-merged>.widget-header button[data-cw-collapse-all]')
            assert await button.count()==1,'Header collapse-all native button missing'
            assert not await button.is_visible()
            for i in range(2):await disclosures.nth(i).locator('summary').click()
            await page.wait_for_timeout(100)
            assert await button.is_visible()
            assert await page.get_by_role('button',name='Hide containers ↑',exact=True).count()==1,'Duplicate Hide containers controls'
            expanded=await page.evaluate(MEASURE)
            assert all(abs(a['x']-b['x'])<2 for a,b in zip(expanded['columns'],expanded['headers'])),expanded
            assert await button.inner_text()=='Hide containers ↑'
            await button.focus();await page.wait_for_timeout(2300)
            assert await button.evaluate('e=>e===document.activeElement'),'Header focus lost on refresh'
            assert await page.locator('.cw-docker[open]').count()==2
            await page.keyboard.press('Enter');await page.wait_for_timeout(100)
            assert await page.locator('.cw-docker[open]').count()==0
            assert not await button.is_visible()
            assert await disclosures.first.locator('summary').evaluate('e=>e===document.activeElement')
            await disclosures.first.locator('summary').click();await button.focus();await page.keyboard.press('Space');await page.wait_for_timeout(100)
            assert await page.locator('.cw-docker[open]').count()==0
            await disclosures.first.locator('summary').click()
            anchor=disclosures.first.locator('.cw-container').first
            await anchor.focus();href=await anchor.get_attribute('href');await page.wait_for_timeout(2300)
            assert await page.evaluate('document.activeElement.getAttribute("href")')==href
            assert await disclosures.first.evaluate('e=>e.open')
            await disclosures.first.locator('summary').click()
            assert not await disclosures.first.evaluate('e=>e.open')
            # Closing one disclosure must not hide the global control while another is open.
            for i in range(2):await disclosures.nth(i).locator('summary').click()
            await disclosures.first.locator('summary').click();await page.wait_for_timeout(100)
            assert await button.is_visible()
            await button.click();await page.wait_for_timeout(100)
            unmatched=page.locator('.cw-unmatched-host')
            if await unmatched.count():
                await unmatched.first.evaluate('e=>{e.parentElement.closest("details").open=true;e.open=true}')
                await page.wait_for_timeout(100)
                assert await button.is_visible()
                await button.click();await page.wait_for_timeout(100)
                assert not await unmatched.first.evaluate('e=>e.open')
            cadence=await page.evaluate('workloadUpdates.slice(1).map((v,i)=>v-workloadUpdates[i])')
            assert len(cadence)>4 and max(cadence)<2500,cadence
            assert await page.locator('.cw-merged .cw-docker-stats,.cw-merged .cw-collapse-bar,.cw-merged .cw-hide-hint').count()==0
            assert await page.locator('.cw-merged .cw-container').count()>0
            assert await page.locator('.cw-workload>a[title*="Proxmox"]').count()>0
            for m in measurements:
                assert not m['overflow'],m
                assert len(m['grid'].split())==3,m
                assert m['columns'][0]['width']>{1600:240,1024:180,390:104}[m['viewport']],m
                if m['viewport']>1000:
                    assert m['docker']['width']<=180,m
                    assert all(abs(a['x']-b['x'])<2 for a,b in zip(m['columns'],m['headers'])),m
            assert not errors,errors
        print(json.dumps({'mode':mode,'measurements':measurements,'errors':errors,'cadence_ms':cadence if mode!='baseline' else [],'behavior_checks_passed':mode!='baseline'},indent=2))
        await browser.close()
if __name__=='__main__':asyncio.run(main())
