"""Read-only deployed delivery verification; intercept row clicks, never navigate items."""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
    url,out=sys.argv[1:3];out=Path(out);out.mkdir(parents=True,exist_ok=True);report=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in [360,390,1600]:
            for light in [False,True]:
                page=await browser.new_page(viewport={'width':width,'height':1000},is_mobile=width<600,has_touch=width<600)
                await page.goto(url+'/media');await page.wait_for_selector('.mo-arr-delivery')
                if light:await page.locator('.theme-choices [data-key="catppuccin-latte"]').first.evaluate('e=>e.click()')
                assert await page.locator('.mo-arr-delivery').count()==2
                for i,app in enumerate(['sonarr','radarr']):
                    widget=page.locator('.mo-arr-delivery').nth(i)
                    queue=await widget.locator('.mo-download').count();imports=await widget.locator('.mo-import').count()
                    details=widget.locator('.mo-imports')
                    await details.evaluate('e=>e.open=true')
                    row=widget.locator('.mo-import').first
                    assert imports>0,'No live imports to verify'
                    await row.evaluate('e=>e.scrollIntoView({block:"center",behavior:"instant"})')
                    result=await row.evaluate('''e=>{const a=e.querySelector('.mo-item-title'),b=e.getBoundingClientRect();return {href:a.getAttribute('href'),nested:!!e.querySelector('a a'),hits:[[3,3],[b.width-3,3],[3,b.height-3],[b.width-3,b.height-3],[b.width/2,b.height/2]].map(([x,y])=>{const hit=document.elementFromPoint(b.x+x,b.y+y)?.closest('a');return hit===a||hit?.classList.contains('mo-imdb')})}}''')
                    assert all(result['hits']) and not result['nested'],result
                    assert result['href'].startswith('https://'+app+'.graymatter.ch/')
                    b=await row.bounding_box()
                    await page.evaluate('''()=>{window.qaDestination=null;document.addEventListener('click',e=>{e.preventDefault();window.qaDestination=e.target.closest('a')?.getAttribute('href')},{capture:true,once:true})}''')
                    await page.mouse.click(b['x']+3,b['y']+3)
                    assert await page.evaluate('window.qaDestination')==result['href']
                    if await row.locator('.mo-imdb').count():await row.locator('.mo-imdb').click(trial=True)
                    await row.locator('.mo-item-title').focus();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab')
                    assert await row.locator('.mo-item-title').evaluate('e=>e===document.activeElement && getComputedStyle(e,"::after").outlineStyle!=="none"')
                    report.append({'app':app,'width':width,'light':light,'liveQueue':queue,'liveImports':imports,'fullRowHit':True,'keyboard':True})
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.screenshot(path=str(out/f'expanded-{width}-{"light" if light else "dark"}.png'),full_page=True)
                await page.locator('.mo-imports').evaluate_all('els=>els.forEach(e=>e.open=false)')
                await page.evaluate('scrollTo(0,0)')
                await page.screenshot(path=str(out/f'delivery-{width}-{"light" if light else "dark"}.png'),full_page=True)
                await page.close()
        await browser.close()
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':asyncio.run(main())
