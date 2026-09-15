"""Read-only staged real-session identity geometry + screenshots (never starts playback)."""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url,out=sys.argv[1:3];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for theme in ['dark','light']:
            for width in [360,390,1600]:
                page=await browser.new_page(viewport={'width':1600,'height':1000})
                await page.goto(url+'/media');await page.wait_for_selector('.mo-player')
                if theme=='light':
                    await page.locator('.header-container .theme-picker').hover()
                    await page.locator('.theme-choices [data-key="catppuccin-latte"]:visible').first.click()
                await page.mouse.move(5,950)
                await page.set_viewport_size({'width':width,'height':1000})
                rows=await page.locator('.mo-player').evaluate_all('''cards=>cards.map(c=>{
                    const v=c.querySelector('.mo-session-viewer'),u=v.querySelector('strong'),l=v.querySelector('.mo-session-user-label'),t=c.querySelector('h3'),b=c.querySelector('button');
                    const r=v.getBoundingClientRect(),br=b.getBoundingClientRect();
                    return {height:c.getBoundingClientRect().height,label:l?.textContent,userVisible:u.scrollWidth<=u.clientWidth+1,userSize:getComputedStyle(u).fontSize,userWeight:getComputedStyle(u).fontWeight,aboveTitle:r.bottom<=t.getBoundingClientRect().top,separated:parseFloat(getComputedStyle(v).borderBottomWidth)>0,infoClear:r.right<=br.left,link:!!c.querySelector('a.mo-player-link[href]'),progress:!!c.querySelector('.mo-progress'),origin:!!c.querySelector('.mo-session-origin'),state:!!c.querySelector('.mo-badge')};
                })''')
                assert rows and all(r['label']=='USER' and r['userVisible'] and r['aboveTitle'] and r['separated'] and r['infoClear'] and r['link'] and r['progress'] and r['origin'] and r['state'] for r in rows),rows
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                button=page.locator('.mo-session-meta button').first
                await button.focus();await page.keyboard.press('Enter')
                assert await page.locator('.mo-session-tooltip').first.evaluate('e=>e.matches(":popover-open")')
                await page.keyboard.press('Escape')
                assert not await page.locator('.mo-session-tooltip').first.evaluate('e=>e.matches(":popover-open")')
                await page.evaluate('scrollTo(0,0)')  # Avoid a stale locator during native one-second refresh.
                await page.screenshot(path=str(out/f'{theme}-{width}.png'),full_page=True)
                results.append({'theme':theme,'width':width,'rows':rows});await page.close()
        await browser.close()
    (out/'report.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))

if __name__=='__main__':asyncio.run(main())
