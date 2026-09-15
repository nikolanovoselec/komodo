"""Read-only actual mobile layout checks; never start radio or Plex playback.
Usage: python qa_mobile_repair.py BASE_URL OUTPUT CHECK [--candidate]
CHECK: sessions, graph, radio, navigation, all. Candidate routes CSS only.
"""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
async def main():
    url,out,check=sys.argv[1:4];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    candidate='--candidate' in sys.argv;report=[];failures=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in [390,360,1600]:
            page=await browser.new_page(viewport={'width':width,'height':900},is_mobile=width<600,has_touch=width<600)
            requests=[];page.on('request',lambda r:requests.append(r.url) if '/radio/queue' in r.url or '/radio/stream/' in r.url else None)
            if candidate:
                async def css(route):
                    name=route.request.url.split('/')[-1].split('?')[0]
                    await route.fulfill(path=str(ROOT/'assets'/name),content_type='text/css')
                for name in ['media-ops.css','plex-radio.css','command-center.css']:
                    await page.route('**/assets/'+name+'*',css)
            await page.goto(url+'/media');await page.wait_for_selector('.mo-traffic')
            if '--light' in sys.argv:
                await page.set_viewport_size({'width':1600,'height':900})
                await page.locator('.header-container .theme-picker').hover()
                await page.locator('.theme-choices [data-key="catppuccin-latte"]:visible').first.click()
                await page.locator('.mo-head h2').click()
                await page.mouse.move(1000,800)
                await page.set_viewport_size({'width':width,'height':900})
            await page.wait_for_timeout(500)
            sizes=await page.evaluate('''()=>Object.fromEntries(['.mo-player','.mo-traffic','.plex-radio','.cc-page-select'].map(s=>[s,[...document.querySelectorAll(s)].map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))]))''')
            report.append({'width':width,'sizes':sizes,'sessions':await page.locator('.mo-player').count()})
            if check in ['sessions','all']:
                if not sizes['.mo-player']:failures.append('No actual sessions; session size unverified')
                elif not all(123<=x['height']<=160 for x in sizes['.mo-player']):failures.append(f'{width}: session cards must retain room for the prominent USER row without exceeding 160px')
            if check in ['graph','all']:
                if sizes['.mo-traffic'][0]['height']>195:failures.append(f'{width}: graph widget exceeds 195px')
                assert await page.locator('.mo-traffic svg').count()==1
            if check in ['radio','all'] and width<600:
                if sizes['.plex-radio'][0]['height']>225:failures.append(f'{width}: radio exceeds 225px')
                if not await page.locator('.pr-controls button').evaluate_all('es=>es.every(e=>{const b=e.getBoundingClientRect();return b.width>=44&&b.height>=44&&b.left>=0&&b.right<=innerWidth})'):failures.append(f'{width}: radio controls clipped or too small')
            if check in ['navigation','all'] and width<600:
                select=page.locator('.cc-page-select');assert await select.is_visible()
                await page.evaluate('scrollTo(0,700)');await page.wait_for_timeout(200)
                if not await select.evaluate('e=>{const r=e.getBoundingClientRect();return r.y>=0&&r.bottom<150}'):failures.append(f'{width}: page dropdown disappears when scrolling')
                for route in ['/hardware-workloads','/endpoints-services','/media']:
                    await select.select_option(route);await page.wait_for_url('**'+route);await page.wait_for_selector('.page-columns')
                    assert await page.locator('.cc-page-select').input_value()==route
            await page.evaluate('scrollTo(0,0)')
            await page.screenshot(path=str(out/f'{check}-{width}.png'),full_page=True)
            for selector,name in [('.mo-players','sessions'),('.mo-traffic','graph'),('.plex-radio','radio')]:
                if await page.locator(selector).count():await page.locator(selector).first.screenshot(path=str(out/f'{check}-{width}-{name}.png'))
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
            assert not requests,requests
            await page.close()
        await browser.close()
    (out/(check+'.json')).write_text(json.dumps({'measurements':report,'failures':failures},indent=2))
    print(json.dumps({'measurements':report,'failures':failures},indent=2));assert not failures,failures
if __name__=='__main__':asyncio.run(main())
