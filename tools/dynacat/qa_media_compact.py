"""Compact Plex-session regression against local Dynacat rendering real captured data.
No Plex controls. BASELINE CANDIDATE OUTPUT; candidate assets/config stay local.
"""
import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    baseline,candidate,out=sys.argv[1:4];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report={};failures=[]
    live_routed='--live-routed' in sys.argv
    from urllib.request import urlopen
    live='http://192.168.2.72:8080'
    live_html=urlopen(live+'/api/pages/media/content/').read().decode() if live_routed else ''
    def players(html):
        start=html.index('<div class="mo-players">')
        end=html.index('<div class="mo-section"><h3>Media servers',start)
        return html[start:end]
    async with async_playwright() as p:
        browser=await p.chromium.launch(args=['--no-sandbox'])
        for theme in ['midnight-navy','catppuccin-latte']:
            for width,height in [(1600,1100),(390,844)]:
                key=f'{theme}-{width}';report[key]={}
                for kind,url in [('baseline',baseline),('candidate',candidate)]:
                    page=await browser.new_page(viewport={'width':1600,'height':1100})
                    await page.goto(url+'/media');await page.wait_for_selector('.mo-player')
                    if live_routed:
                        fragment=await page.locator('.mo-players').evaluate('e=>e.outerHTML')
                        routed=live_html.replace(players(live_html),fragment+'\n').replace('<h3>Now playing</h3>','<h3>Now playing · STAGED captured sessions</h3>')
                        css=(Path('/srv/hermes/workspaces/media-compact-qa')/kind/'assets/media-ops.css').read_text()
                        await page.route('**/assets/media-ops.css',lambda r:r.fulfill(body=css,content_type='text/css'))
                        await page.route('**/api/pages/media/content/',lambda r:r.fulfill(body=routed,content_type='text/html'))
                        await page.route('**/api/sse/**',lambda r:r.abort())
                        await page.route('**/api/widgets/**',lambda r:r.abort())
                        await page.goto(live+'/media');await page.wait_for_selector('.mo-player')
                    await page.locator('.header-container .theme-picker').hover()
                    await page.locator(f'.theme-choices [data-key="{theme}"]:visible').first.click()
                    await page.locator('.mo-section h3').first.click()
                    await page.keyboard.press('Escape')
                    await page.mouse.move(1000,1000)
                    await page.set_viewport_size({'width':width,'height':height})
                    await page.wait_for_timeout(400)
                    assert await page.locator('html').get_attribute('data-theme')==theme
                    bounds=await page.locator('.mo-player').evaluate_all('es=>es.map(e=>({height:e.getBoundingClientRect().height,width:e.getBoundingClientRect().width,title:e.querySelector("h3").textContent,href:e.querySelector(".mo-player-link").getAttribute("href")}))')
                    report[key][kind]={'cards':bounds,'section_height':(await page.locator('.mo-players').bounding_box())['height']}
                    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    await page.screenshot(path=str(out/f'{kind}-{key}.png'),full_page=True)
                    await page.locator('.mo-players').screenshot(path=str(out/f'{kind}-{key}-sessions.png'))
                    if kind=='candidate':
                        assert await page.locator('.mo-player-art img').evaluate_all('es=>es.every(e=>e.complete&&e.naturalWidth>0&&e.closest("a.mo-player-link"))')
                        assert await page.locator('.mo-player h3').evaluate_all('es=>es.every(e=>e.closest("a.mo-player-link")&&parseFloat(getComputedStyle(e).fontSize)>=14)')
                        assert await page.locator('.mo-player .mo-progress').evaluate_all('es=>es.every(e=>e.getBoundingClientRect().height===3)')
                        source=json.loads((out.parent/'source/media-current').read_text())
                        expected=[f"{s['bandwidth_kbps']} kbps" for s in source['sessions']['data']['streams']]
                        assert await page.locator('.mo-session-bandwidth').all_text_contents()==expected
                        if not await page.locator('.mo-session-meta').count():failures.append(f'{key}: missing accessible secondary information')
                        else:
                            controls=page.locator('.mo-session-meta summary,.mo-session-meta button')
                            async def opened(index):
                                return await page.locator('.mo-session-meta').nth(index).evaluate("e=>e.matches('details[open]') || !!e.querySelector(':popover-open')")
                            await controls.first.focus()
                            await page.keyboard.press('Enter')
                            assert await opened(0)
                            await page.screenshot(path=str(out/f'tooltip-{key}.png'),full_page=True)
                            await page.locator('.mo-session-tooltip:visible').screenshot(path=str(out/f'tooltip-{key}-detail.png'))
                            assert await page.locator('.mo-session-tooltip:visible').evaluate('e=>{const b=e.getBoundingClientRect();return b.x>=0&&b.right<=innerWidth}'), 'Popover exceeds viewport'
                            await page.keyboard.press('Enter')
                            assert not await opened(0)
                            await page.add_script_tag(url=live+'/assets/media-ops.js')
                            await controls.nth(1).click()
                            await page.wait_for_timeout(100)
                            await page.locator('.media-ops-widget').first.evaluate("w=>document.dispatchEvent(new CustomEvent('dynacat:widget-updated',{detail:{widget:w}}))")
                            assert not await opened(0),'Opening second session incorrectly reopens first session after refresh'
                            assert await opened(1),'Second session information should remain open'
                    await page.close()
                a,b=report[key]['baseline'],report[key]['candidate']
                assert [x['href'] for x in a['cards']]==[x['href'] for x in b['cards']]
                reductions=[round((1-y['height']/x['height'])*100,2) for x,y in zip(a['cards'],b['cards'])]
                report[key]['reduction_percent']=reductions
                if not all(40<=x<=55 for x in reductions):failures.append(f'{key}: expected 40–55% shorter cards; got {reductions}')
        await browser.close()
    report['failures']=failures
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2));assert not failures,failures

if __name__=='__main__':asyncio.run(main())
