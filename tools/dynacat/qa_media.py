"""Run against the actual staged/live app, never fixture server responses."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url=sys.argv[1].rstrip('/')+'/media'; out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1600,'height':1100})
        errors=[];writes=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:writes.append(r.url) if r.method!='GET' else None)
        await page.goto(url);await page.wait_for_selector('.mo-server');await page.wait_for_timeout(13000)
        await page.evaluate("window.mediaUpdates=[];document.addEventListener('dynacat:widget-updated', e=>{if(e.detail.widget.querySelector('.mo-live'))mediaUpdates.push(performance.now())})")
        details=page.locator('.mo-imports').first
        await details.locator('summary').click()
        await details.locator('summary').focus()
        await page.wait_for_timeout(12000)
        assert not await details.evaluate('(e)=>e.open'), 'Disclosure lost through refresh'
        assert await page.evaluate("document.activeElement.matches('.mo-imports summary')"), 'Focus lost through refresh'
        await details.locator('summary').click()
        cadence=await page.evaluate('mediaUpdates.slice(1).map((v,i)=>v-mediaUpdates[i])')
        assert len(cadence)>=5 and max(cadence)<2500,cadence
        variants=[]
        for theme in ['catppuccin-latte','midnight-navy']:
            await page.locator('.header-container .theme-picker').hover()
            await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click()
            await page.wait_for_timeout(500);await page.reload();await page.wait_for_selector('.mo-server')
            assert await page.locator('html').get_attribute('data-theme')==theme
            for width,height in [(1600,1100),(1024,1000),(768,1000),(390,844)]:
                await page.set_viewport_size({'width':width,'height':height});await page.evaluate('scrollTo(0,0)');await page.wait_for_timeout(300)
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
                assert await page.locator('.mo-delivery').first.is_visible(),width
                file=f'{width}-{theme}.png';await page.screenshot(path=str(out/file),full_page=True)
                variants.append({'width':width,'theme':theme,'screenshot':file})
            await page.set_viewport_size({'width':1600,'height':1100})
        images=await page.locator('.mo-art img').evaluate_all('(imgs)=>({count:imgs.length,loaded:imgs.filter(i=>i.complete&&i.naturalWidth).length,unsafe:imgs.filter(i=>!i.src.startsWith("data:image/jpeg;base64,")).length})')
        assert images['count']==images['loaded'] and images['unsafe']==0,images
        assert not errors,errors
        assert not writes,writes
        report=dict(variants=variants,images=images,errors=errors,writes=writes,cadence_ms=cadence,focus_preserved=True,disclosure_preserved=True)
        (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
        await browser.close()

asyncio.run(main())
