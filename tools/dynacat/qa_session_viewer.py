"""Read-only viewer/location visibility regression on actual Plex session cards.
Usage: python qa_session_viewer.py BASE_URL OUTPUT [--light]
Never starts playback. No sessions means verification is unavailable, not success.
"""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url,out=sys.argv[1:3];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in [360,390,1600]:
            page=await browser.new_page(viewport={'width':1600,'height':900})
            await page.goto(url+'/media');await page.wait_for_selector('.mo-players')
            if '--light' in sys.argv:
                await page.locator('.header-container .theme-picker').hover()
                await page.locator('.theme-choices [data-key="catppuccin-latte"]:visible').first.click()
                await page.locator('.mo-head h2').click()
            await page.mouse.move(1000,800)
            await page.set_viewport_size({'width':width,'height':900})
            rows=await page.locator('.mo-player').evaluate_all('''cards=>cards.map(c=>{
              const v=c.querySelector('.mo-session-viewer'),o=c.querySelector('.mo-session-origin');
              const tip=c.querySelectorAll('.mo-session-tooltip p');
              const expected=tip[0].textContent.split(' · ');
              const location=tip[1].textContent.split(' · ').at(-1).trim();
              const visible=e=>!!e&&!!e.getBoundingClientRect().height&&getComputedStyle(e).visibility!=='hidden'&&e.scrollWidth<=e.clientWidth+1;
              return {viewer:visible(v),origin:visible(o),matchedUser:!!v&&v.textContent.includes(expected[0].trim()),matchedPlayer:!!o&&o.textContent.includes(expected.slice(1).join(' · ').trim()),matchedLocation:!!v&&v.textContent.toLowerCase().includes(location),height:c.getBoundingClientRect().height,link:!!c.querySelector('a.mo-player-link[href]')};
            })''')
            assert rows,'No live sessions; cannot verify viewer visibility'
            assert all(r['viewer'] and r['origin'] and r['matchedUser'] and r['matchedPlayer'] and r['matchedLocation'] for r in rows),rows
            assert all(123<=r['height']<=180 for r in rows),rows  # USER plus approximate location may wrap on phones.
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
            await page.locator('.mo-section h3').filter(has_text='Now playing').click()
            await page.mouse.move(5,890)
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(500)
            # Native one-second refresh can detach a locator during capture.
            await page.screenshot(path=str(out/f'sessions-{width}.png'),full_page=True)
            results.append({'width':width,'sessions':rows});await page.close()
        await browser.close()
    (out/'report.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
if __name__=='__main__':asyncio.run(main())
