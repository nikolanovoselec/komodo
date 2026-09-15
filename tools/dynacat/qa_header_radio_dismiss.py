"""Header and dismiss QA. --staged uses labeled media-layout navigation fixtures.
Live mode exercises actual page navigation; --playback verifies real muted audio.
"""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
    url,out=sys.argv[1:3];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    staged='--staged' in sys.argv;rows=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in [390,1600]:
            page=await browser.new_page(viewport={'width':width,'height':900})
            if '--candidate-header' in sys.argv:
                await page.route('**/assets/command-center.css*',lambda route:route.fulfill(path=str(Path(__file__).parent/'assets/command-center.css'),content_type='text/css'))
            await page.goto(url+'/media');await page.wait_for_selector('#plex-radio')
            assert (await page.locator('.header-container .logo').inner_text()).strip()=='THE CONSTRUCT'
            assert await page.locator('.header-container .nav-item-icon').count()==0
            labels=await page.locator('.header-container .nav-item').evaluate_all('es=>es.map(e=>[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(""))')
            assert await page.locator('.header-container .nav-keybind-hint').evaluate_all('es=>es.every(e=>getComputedStyle(e).display==="none")')
            assert [x.strip() for x in labels]==['HARDWARE & WORKLOADS','MEDIA','ENDPOINTS & SERVICES'],labels
            assert await page.locator('.header-container .nav-item + .nav-item').evaluate_all('es=>es.every(e=>getComputedStyle(e,"::before").content===\'"|"\')')
            if width>=768:
                geometry=await page.locator('.header-container .nav-item').evaluate_all('''es=>es.slice(1).map((e,i)=>{
                  const text=n=>{const r=document.createRange();r.selectNodeContents(n);return r.getBoundingClientRect()};
                  const before=getComputedStyle(e,'::before'),r=e.getBoundingClientRect();
                  const center=r.left+parseFloat(before.left)+parseFloat(before.width)/2+new DOMMatrixReadOnly(before.transform).m41;
                  const a=text(es[i]),b=text(e);return {gap:b.left-a.right,error:center-(a.right+b.left)/2};
                })''')
                assert all(abs(g['error'])<1 for g in geometry),geometry
                assert abs(geometry[0]['gap']-geometry[1]['gap'])<1,geometry
            await page.screenshot(path=str(out/f'header-{width}.png'))
            assert not await page.locator('.pr-dismiss').is_visible()
            if '--playback' in sys.argv:
                await page.locator('#plex-radio-audio').evaluate('e=>e.muted=true')
                await page.locator('[data-action="shuffle"]').click()
                for _ in range(60):
                    if await page.locator('#plex-radio-audio').evaluate('e=>!e.paused && e.currentTime>1'):break
                    await page.wait_for_timeout(500)
                else:raise AssertionError(await page.locator('.pr-status').inner_text())
            async def navigate(path):
                if staged:await page.evaluate('path=>history.pushState({},"",path)',path)
                elif width<600:await page.locator('.cc-page-select').select_option(path)
                else:await page.locator('.header-container .nav-item[href="'+path+'"]').click()
                await page.wait_for_url('**'+path)
                await page.wait_for_timeout(200)
            await navigate('/hardware-workloads')
            b=await page.locator('.pr-dismiss').bounding_box();assert b and b['width']>=44 and b['height']>=44
            await page.locator('#plex-radio').screenshot(path=str(out/f'mini-{width}.png'))
            await page.locator('.pr-dismiss').click()
            assert not await page.locator('#plex-radio').is_visible()
            await navigate('/endpoints-services')
            assert not await page.locator('#plex-radio').is_visible()
            if '--playback' in sys.argv:
                before=await page.locator('audio').evaluate('e=>e.currentTime')
                await page.wait_for_timeout(1200)
                assert await page.locator('audio').evaluate('e=>!e.paused && e.currentTime>'+str(before))
            await navigate('/media')
            assert await page.locator('#plex-radio').is_visible()
            assert not await page.locator('.pr-dismiss').is_visible()
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
            rows.append({'width':width,'header':True,'dismiss':True,'returnsOnMedia':True,'realPlaybackVerified':'--playback' in sys.argv})
            await page.close()
        await browser.close()
    (out/'report.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
if __name__=='__main__':asyncio.run(main())
