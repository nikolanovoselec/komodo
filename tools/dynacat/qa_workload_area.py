"""Captured-real native renderer comparison. No deployment or playback."""
import asyncio, copy, json, subprocess, sys
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
ROOT=Path(__file__).parent
OUT=ROOT.parents[2]/'workloads-area-qa'
def run(*a): return subprocess.check_output(a,text=True)
def prepare(variant):
    cfg=yaml.safe_load((OUT/'backup/config/dynacat.yml').read_text())
    origin=ROOT/'config/dynacat.yml' if variant=='candidate' else (Path('/tmp/workloads-static.yml') if variant=='static' else OUT/'backup/config/dynacat.yml')
    data=yaml.safe_load(origin.read_text())
    widget=next(w for p in data['pages'] for c in p['columns'] for w in c['widgets'] if w.get('title')=='Workloads')
    widget['url']='http://workload-area-source:8090/current.json';widget['cache']='1s'
    cfg['pages']=[dict(name='Workloads QA',slug='workloads',columns=[dict(size='full',widgets=[widget])])]
    cfg['server']['port']=8080;cfg['server']['cache-dir']='/tmp/cache'
    cfg['document']['head']+='<link rel="stylesheet" href="/assets/telemetry-history.css">'
    folder=OUT/variant;folder.mkdir(exist_ok=True)
    (folder/'dynacat.yml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    subprocess.run(['docker','rm','-f','workload-area-renderer'],capture_output=True)
    assets=ROOT/'assets' if variant=='candidate' else OUT/'backup/assets'
    run('docker','run','-d','--name','workload-area-renderer','--network','media-compact-qa','-p','127.0.0.1:18141:8080','-v',f'{folder}:/app/config:ro','-v',f'{assets}:/app/assets:ro','panonim/dynacat:3.0.0')
async def inspect(variant,url):
    async with async_playwright() as p:
        browser=await p.chromium.launch();page=await browser.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        for retry in range(20):
            try:
                await page.goto(url);await page.wait_for_selector('.cw-workload',timeout=10000);break
            except Exception:
                if retry==19: raise
                await asyncio.sleep(.3)
        result=[]
        for theme in ['midnight-navy','catppuccin-latte']:
            await page.locator(f'.theme-choices [data-key="{theme}"]').first.evaluate('e=>e.click()')
            for width in [1600,390]:
                await page.set_viewport_size(dict(width=width,height=1100));await page.wait_for_timeout(300)
                box=await page.locator('.cw-workloads').bounding_box()
                stats=await page.locator('.cw-workload').evaluate_all('es=>es.map(e=>({height:e.getBoundingClientRect().height,link:e.querySelector("a").getBoundingClientRect().height,summary:e.querySelector("summary").getBoundingClientRect().height}))')
                await page.screenshot(path=str(OUT/f'{variant}-{theme}-{width}-page.png'),full_page=True)
                await page.locator('.cw-workloads').screenshot(path=str(OUT/f'{variant}-{theme}-{width}.png'))
                graph=page.locator('.cw-history-chart').first
                height=(await graph.bounding_box())['height'] if await graph.count() else None
                result.append(dict(theme=theme,width=width,rows=stats,section=box['height'],chart=height,graphs=await page.locator('.cw-history-chart').count()))
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                if variant=='candidate':
                    assert height is not None and height<=28, f'chart too tall: {height}'
                    ink=await page.locator('.pve-guest-cpu .cw-history-line').first.evaluate('e=>getComputedStyle(e).stroke')
                    assert ink == ('rgb(40, 102, 173)' if theme=='catppuccin-latte' else 'rgb(131, 185, 244)'), ink
                    assert await page.locator('.cw-history-area').count()==27
                    assert await page.locator('.cw-history-area').evaluate_all('es=>es.some(e=>e.getAttribute("d").length>0)')
                    assert all(x['link']>=44 and x['summary']>=44 for x in stats)
        if variant=='candidate':
            summary=page.locator('.cw-docker summary').first
            await summary.focus();await page.keyboard.press('Enter');assert await summary.evaluate('e=>e.parentElement.open')
            await page.keyboard.press('Enter');assert not await summary.evaluate('e=>e.parentElement.open')
            link=page.locator('.cw-workload a').first;await link.focus();assert await link.evaluate('e=>e===document.activeElement && e.href.length>0')
        (OUT/f'{variant}-report.json').write_text(json.dumps(dict(measurements=result,errors=errors),indent=2));print(json.dumps(result));await browser.close()
if __name__=='__main__':
    variant=sys.argv[1]
    if variant!='live': prepare(variant)
    asyncio.run(inspect(variant,'http://192.168.2.72:8080/hardware-workloads' if variant=='live' else 'http://127.0.0.1:18141/workloads'))
