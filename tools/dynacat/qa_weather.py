"""Native weather and branding regression; run with QA venv, URL and output prefix."""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url, prefix = sys.argv[1:3]
    report = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--no-sandbox'])
        for mode, width, height in [('desktop',1600,1100),('mobile',390,844)]:
            page = await browser.new_page(viewport={'width':width,'height':height})
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_selector('.weather-bar')
            weather = page.locator('.cc-rail-weather')
            await weather.scroll_into_view_if_needed()
            await page.wait_for_timeout(1200)
            text = await weather.inner_text()
            assert 'Bern' in text and '°C' in text, text
            assert await page.get_by_text('The Construct',exact=True).count() > 0
            assert 'There is no spoon' not in await page.locator('body').inner_text()
            assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert await page.locator('.weather-column-current').count()==1
            assert await page.locator('.weather-column-daylight').count()>0
            bars = await page.locator('.weather-bar').evaluate_all('(es)=>es.map(e=>({height:e.getBoundingClientRect().height,width:e.getBoundingClientRect().width}))')
            assert len(bars)==12 and all(x['height']>0 and x['width']>0 for x in bars), bars
            if '127.0.0.1' not in url:  # isolated weather stage has no collector service
                assert await page.locator('.pve-node').count()==3
            assert await page.locator('.widget-type-bookmarks,.widget-type-releases').count()==0
            await weather.screenshot(path=prefix+'-'+mode+'-weather.png')
            await page.evaluate('scrollTo(0,0)')
            await page.screenshot(path=prefix+'-'+mode+'.png',full_page=True)
            await page.screenshot(path=prefix+'-'+mode+'-viewport.png')
            themes = []
            if mode=='desktop':
                keys = await page.locator('.header-container .theme-choices [data-key]').evaluate_all('(es)=>es.map(e=>e.dataset.key)')
                assert len(keys)==22, keys
                for key in keys:
                    await page.evaluate('scrollTo(0,0)')
                    await page.locator('.header-container .theme-picker').hover()
                    if await page.locator('html').get_attribute('data-theme') == key:
                        themes.append(key)
                        continue
                    await page.locator(f'.theme-choices [data-key="{key}"]:visible').first.click()
                    await page.wait_for_timeout(250)
                    assert await page.locator('html').get_attribute('data-theme')==key
                    await weather.scroll_into_view_if_needed()
                    assert await page.locator('.weather-columns').is_visible()
                    assert await page.locator('.weather-bar').first.evaluate('e=>e.getBoundingClientRect().height>0')
                    themes.append(key)
                await page.evaluate('scrollTo(0,0)')
                await page.locator('.header-container .theme-picker').hover()
                await page.locator('.theme-choices [data-key="catppuccin-latte"]:visible').first.click()
                await page.wait_for_timeout(300)
                await weather.screenshot(path=prefix+'-light-weather.png')
            report[mode]={'text':text,'bars':bars,'themes':themes,'overflow':False,'branding':'The Construct'}
            await page.close()
        await browser.close()
    Path(prefix+'-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

asyncio.run(main())
