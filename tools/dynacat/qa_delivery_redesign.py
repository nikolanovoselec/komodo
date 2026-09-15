"""Captured-real-data native ARR comparison. Read-only source; local stage only."""
import asyncio, json, subprocess, hashlib
from pathlib import Path
import yaml
from playwright.async_api import async_playwright
import qa_delivery
ROOT=Path(__file__).parent
OUT=ROOT.parents[2]/'delivery-redesign-evidence'
BASE=ROOT.parents[2]/'delivery-redesign-baseline'

async def capture(label):
    reports=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for width in (360,390,1600):
            for light in (False,True):
                page=await browser.new_page(viewport={'width':width,'height':1000},is_mobile=width<600,has_touch=width<600)
                await page.goto('http://127.0.0.1:18129/media')
                await page.wait_for_selector('.mo-arr-delivery')
                await page.add_style_tag(content='*{animation:none!important;transition:none!important;scroll-behavior:auto!important}')
                if light: await page.locator('.theme-choices [data-key="catppuccin-latte"]').first.evaluate('e=>e.click()')
                await page.screenshot(path=str(OUT/f'{label}-{width}-{light}-default.png'),full_page=True)
                dimensions=await page.locator('.mo-arr-delivery').evaluate_all('es=>es.map(e=>({height:e.getBoundingClientRect().height,historyOpen:e.querySelector("details").open,imports:e.querySelectorAll(".mo-import").length}))')
                await page.locator('.mo-imports').evaluate_all('es=>es.forEach(e=>e.open=true)')
                await page.wait_for_timeout(100)
                await page.screenshot(path=str(OUT/f'{label}-{width}-{light}-history.png'),full_page=True)
                if label=='candidate':
                    assert all(not d['historyOpen'] for d in dimensions)
                    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    source_path=qa_delivery.OUT/'source/captured-arr'
                    original=source_path.read_text()
                    changed=json.loads(original)
                    for value in changed.values():
                        value['data']['recent'][0]['subtitle'] += ' [refresh-test fixture]'
                    source_path.write_text(json.dumps(changed))
                    await page.evaluate('window.qaRefresh=0;document.addEventListener("dynacat:widget-updated",()=>window.qaRefresh++)')
                    await page.wait_for_function('()=>[...document.querySelectorAll(".mo-arr-delivery")].every(e=>e.querySelector(".mo-import p").textContent.includes("[refresh-test fixture]"))',timeout=25000)
                    assert await page.locator('.mo-imports').evaluate_all('es=>es.every(e=>e.open)'), 'Refresh lost expanded history'
                    await page.locator('.mo-imports').evaluate_all('es=>es.forEach(e=>e.open=false)')
                    await page.wait_for_timeout(100)
                    await page.evaluate('window.qaRefresh=0')
                    source_path.write_text(original)
                    await page.wait_for_function('()=>[...document.querySelectorAll(".mo-arr-delivery")].every(e=>!e.querySelector(".mo-import p").textContent.includes("[refresh-test fixture]"))',timeout=25000)
                    assert await page.locator('.mo-imports').evaluate_all('es=>es.every(e=>!e.open)'), 'Refresh reopened collapsed history'
                reports.append(dict(width=width,light=light,widgets=dimensions))
                await page.close()
        await browser.close()
    (OUT/f'{label}.json').write_text(json.dumps(reports,indent=2))

if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    qa_delivery.prepare()
    captured=json.loads((BASE/'captured-arr.json').read_text())
    for label,source in [('baseline',BASE),('candidate',ROOT)]:
        d=yaml.safe_load((source/'config/dynacat.yml').read_text())
        widgets=[w for p in d['pages'] for c in p['columns'] for w in c['widgets'] if w.get('title') in ('Sonarr delivery','Radarr delivery')]
        for w in widgets:
            w['url']='http://delivery-qa-source:8090/captured-arr'
            w['template']='<p>CAPTURED REAL DATA · NOT LIVE</p>'+w['template']
        (qa_delivery.OUT/'source/captured-arr').write_text(json.dumps(captured))
        d['pages']=[dict(name='Delivery QA',slug='media',columns=[dict(size='full',widgets=[dict(type='html',source='<p>CAPTURED REAL DATA · delivery-only comparison</p>')]),dict(size='small',widgets=widgets)])]
        d['document']['head']='<link rel="stylesheet" href="/assets/media-ops.css"><script defer src="/assets/media-ops.js"></script>'
        d['theme'].pop('custom-css-file',None)
        d['server'].update(port=8080,**{'cache-dir':'/tmp/cache'})
        (qa_delivery.OUT/'config/dynacat.yml').write_text(yaml.safe_dump(d,sort_keys=False))
        subprocess.run(['docker','rm','-f','delivery-qa-stage'],check=True,capture_output=True)
        subprocess.run(['docker','run','-d','--name','delivery-qa-stage','--network','media-compact-qa','-p','127.0.0.1:18129:8080','-v',f'{qa_delivery.OUT}/config:/app/config:ro','-v',f'{source}/assets:/app/assets:ro','panonim/dynacat:3.0.0'],check=True,capture_output=True)
        asyncio.run(capture(label))
    print('PASS: captured-real baseline/candidate, 6 layouts each, expanded/collapsed preserved through actual refresh')
