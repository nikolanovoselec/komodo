"""Read-only rendered regression for removal of the bottom news widget."""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    base=sys.argv[1].rstrip('/');out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1600,'height':1100})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(base+'/endpoints-services');await page.wait_for_selector('.es-launcher')
        assert await page.locator('.es-endpoint').count()==86
        assert await page.locator('.endpoints-news-title,#news-digest,.es-news-heading,[href="#news-digest"]').count()==0
        assert 'Article integration pending' not in await page.locator('body').inner_text()
        variants=[]
        for width,height in [(1600,1100),(390,844)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.evaluate('scrollTo(0,document.body.scrollHeight)');await page.wait_for_timeout(500)
            bounds=await page.locator('.es-launcher').evaluate('e=>({bottom:e.getBoundingClientRect().bottom,widgets:e.parentElement.children.length,overflow:document.documentElement.scrollWidth>innerWidth})')
            assert bounds['widgets']==1 and not bounds['overflow'],bounds
            await page.screenshot(path=str(out/f'endpoints-bottom-{width}.png'))
            variants.append(dict(width=width,**bounds))
        await page.goto(base+'/news');await page.wait_for_url(base+'/endpoints-services')
        await page.goto(base+'/media');await page.wait_for_selector('.mo-poster-link');await page.wait_for_selector('.mo-traffic svg')
        media=dict(posters=await page.locator('.mo-poster-link').count(),traffic=await page.locator('.mo-traffic svg').count())
        assert media['posters']>0 and media['traffic']>0
        assert not errors,errors
        report=dict(variants=variants,endpoints=86,media=media,errors=errors)
        (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        await browser.close()

if __name__=='__main__':asyncio.run(main())
